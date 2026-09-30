const loginForm = document.querySelector('.auth-section--login .auth-form');

loginForm?.querySelectorAll('.password-toggle').forEach((button) => {
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

loginForm?.addEventListener('submit', () => {
  const submitButton = loginForm.querySelector('[type="submit"]');
  if (!submitButton || !loginForm.checkValidity()) return;

  submitButton.disabled = true;
  submitButton.querySelector('span:first-child').textContent = 'Signing you in…';
});
