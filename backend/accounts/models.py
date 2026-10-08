import math
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone

# Rules for the emailed sign-up code.
CODE_LIFETIME = timedelta(minutes=10)
MAX_WRONG_ATTEMPTS = 5
RESEND_WAIT = timedelta(seconds=60)
MAX_SENDS_PER_HOUR = 5


class UserManager(DjangoUserManager):
    def create_superuser(self, *args, **extra_fields):
        # Accounts made with createsuperuser don't need to confirm their email.
        extra_fields.setdefault("email_verified", True)
        return super().create_superuser(*args, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True)
    phone=models.CharField(max_length=15, blank=True, null=True)
    role=models.CharField(max_length=50, blank=True, default='customer')
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    # False until the emailed sign-up code is entered. Not the same as is_active,
    # which means "deactivated by staff".
    email_verified = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    recipient_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=15)
    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    area = models.CharField(max_length=100, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient_name} - {self.address_line}"


def make_code():
    """A random 6-digit code, as text (it can start with 0)."""
    return f"{secrets.randbelow(1_000_000):06d}"


class EmailVerification(models.Model):
    """The emailed sign-up code of one unverified user. Only a hash of the code is saved."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_verification"
    )
    # Also kept in the browser session that last set the password. Only that session
    # may use the code, so someone who signs up again with the same email can't
    # take over the account when the real owner enters their code.
    session_token = models.CharField(max_length=64)
    code_hash = models.CharField(max_length=128, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    wrong_attempts = models.PositiveSmallIntegerField(default=0)
    hour_started_at = models.DateTimeField(null=True, blank=True)
    sends_this_hour = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Email code for {self.user}"

    @classmethod
    def claim(cls, user):
        """Give the code to a new browser session. The code itself doesn't change."""
        verification = cls.objects.filter(user=user).first() or cls(user=user)
        verification.session_token = secrets.token_urlsafe(32)
        verification.save()
        return verification

    def token_matches(self, token):
        return bool(token) and secrets.compare_digest(token, self.session_token)

    def seconds_until_resend(self):
        """0 if a new code may be sent now, otherwise how many seconds to wait."""
        now = timezone.now()
        if self.sent_at and now < self.sent_at + RESEND_WAIT:
            return math.ceil((self.sent_at + RESEND_WAIT - now).total_seconds())
        if self.hour_started_at and self.sends_this_hour >= MAX_SENDS_PER_HOUR:
            hour_ends = self.hour_started_at + timedelta(hours=1)
            if now < hour_ends:
                return math.ceil((hour_ends - now).total_seconds())
        return 0

    def save_sent_code(self, code):
        """Remember a code that was just emailed. It replaces any earlier code."""
        now = timezone.now()
        if not self.hour_started_at or now >= self.hour_started_at + timedelta(hours=1):
            self.hour_started_at = now
            self.sends_this_hour = 0
        self.sends_this_hour += 1
        self.code_hash = make_password(code)
        self.sent_at = now
        self.wrong_attempts = 0
        self.save()

    def expires_at(self):
        return self.sent_at + CODE_LIFETIME

    def check_code(self, code):
        """Returns "ok", "wrong", "locked" (too many wrong tries) or "expired"."""
        if not self.code_hash or timezone.now() > self.expires_at():
            return "expired"
        if self.wrong_attempts >= MAX_WRONG_ATTEMPTS:
            return "locked"
        if check_password(code, self.code_hash):
            return "ok"
        self.wrong_attempts += 1
        self.save(update_fields=["wrong_attempts"])
        if self.wrong_attempts >= MAX_WRONG_ATTEMPTS:
            return "locked"
        return "wrong"
