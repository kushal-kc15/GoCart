from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Address


class AddressTestPageTests(TestCase):
    def test_address_page_displays_address_and_user(self):
        user = get_user_model().objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            password="test-password-123",
        )
        address = Address.objects.create(
            user=user,
            recipient_name="Test Customer",
            phone="9800000000",
            address_line="123 Market Street",
            city="Kathmandu",
            area="New Baneshwor",
            is_default=True,
        )

        response = self.client.get(reverse("address_test"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(address, response.context["addresses"])
        self.assertContains(response, address.recipient_name)
        self.assertContains(response, address.city)
        self.assertContains(response, user.email)
