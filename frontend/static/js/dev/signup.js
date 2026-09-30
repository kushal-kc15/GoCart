const signupForm = document.querySelector('.auth-section--signup .auth-form');
// Django renders {{ form.password1 }} with id="id_password1"; fallback to bare id for safety
const passwordInput = document.getElementById('id_password1') || document.getElementById('password1');

signupForm?.querySelectorAll('.password-toggle').forEach((button) => {
  button.addEventListener('click', () => {
    // Try Django's id_ prefix first, then bare id from data-target
    const target = button.dataset.target;
    const input = document.getElementById('id_' + target) || document.getElementById(target);
    if (!input) return;

    const revealPassword = input.type === 'password';
    input.type = revealPassword ? 'text' : 'password';
    button.setAttribute('aria-label', revealPassword ? 'Hide password' : 'Show password');
    button.classList.toggle('is-visible', revealPassword);
  });
});

if (passwordInput) {
  const meter = document.createElement('span');
  meter.className = 'password-strength';
  meter.setAttribute('aria-hidden', 'true');
  meter.innerHTML = '<span class="password-strength__bar"></span>';
  passwordInput.closest('.form-group')?.append(meter);

  passwordInput.addEventListener('input', () => {
    const value = passwordInput.value;
    const checks = [
      value.length >= 8,
      /[a-z]/.test(value) && /[A-Z]/.test(value),
      /\d/.test(value),
      /[^A-Za-z0-9]/.test(value),
    ];
    const score = checks.filter(Boolean).length;
    const bar = meter.firstElementChild;
    bar.style.width = `${score * 25}%`;
    bar.dataset.strength = score >= 4 ? 'strong' : score >= 2 ? 'medium' : 'weak';
  });
}

signupForm?.addEventListener('submit', () => {
  const submitButton = signupForm.querySelector('[type="submit"]');
  if (!submitButton || !signupForm.checkValidity()) return;

  submitButton.disabled = true;
  submitButton.querySelector('span:first-child').textContent = 'Creating your account…';
});
