/* login2.js — Login page: password visibility toggle + tab order + submit guard */

const loginForm = document.querySelector('.auth-section--login .auth-form');

// ── Password visibility toggle ─────────────────────────────────────────────────
loginForm?.querySelectorAll('.password-toggle').forEach((button) => {
  // Remove from tab order so it does not interrupt keyboard flow
  button.setAttribute('tabindex', '-1');

  button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.target);
    if (!input) return;

    const revealPassword = input.type === 'password';
    input.type = revealPassword ? 'text' : 'password';
    button.setAttribute('aria-label', revealPassword ? 'Hide password' : 'Show password');
    button.classList.toggle('is-visible', revealPassword);
  });
});

// ── Tab-order: password → submit button (stops there) ─────────────────────────
const loginPasswordInput = document.getElementById('password');
const loginSubmitButton  = loginForm?.querySelector('[type="submit"]');

if (loginPasswordInput && loginSubmitButton) {
  // Tab inside password field → jump straight to submit
  loginPasswordInput.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.shiftKey) {
      e.preventDefault();
      loginSubmitButton.focus();
    }
  });
}

if (loginSubmitButton) {
  // Tab on submit button stops here (no further tabbing out of the form)
  loginSubmitButton.addEventListener('keydown', (e) => {
    if (e.key === 'Tab' && !e.shiftKey) {
      e.preventDefault();
    }
    // Shift+Tab on submit → go back to password field
    if (e.key === 'Tab' && e.shiftKey && loginPasswordInput) {
      e.preventDefault();
      loginPasswordInput.focus();
    }
  });
}

// ── Prevent double-submit on valid form ───────────────────────────────────────
loginForm?.addEventListener('submit', () => {
  if (!loginSubmitButton || !loginForm.checkValidity()) return;

  loginSubmitButton.disabled = true;
  const label = loginSubmitButton.querySelector('span:first-child');
  if (label) label.textContent = 'Signing you in…';
});
