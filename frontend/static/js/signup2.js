/* signup2.js
   Tab order:  Confirm Password  →  "I agree" checkbox  →  Create Account  (stops)
   Script loads with defer so DOM is ready — no DOMContentLoaded wrapper needed.
*/

const signupForm     = document.querySelector('.auth-section--signup .auth-form');

if (signupForm) {

  const termsCheckbox   = document.getElementById('terms');
  const termsError      = document.getElementById('terms-error');
  const submitBtn       = signupForm.querySelector('[type="submit"]');

  /* Password inputs selected by type+position — no ID dependency at all.
     Index 0 = Password, Index 1 = Confirm Password */
  const pwdInputs  = signupForm.querySelectorAll('input[type="password"]');
  const pwd1       = pwdInputs[0] ?? null;   // Password
  const pwd2       = pwdInputs[1] ?? null;   // Confirm Password  ← Tab trigger

  /* ── Eye-toggle buttons: remove from tab order, find sibling input by wrapper ── */
  signupForm.querySelectorAll('.password-toggle').forEach((btn) => {
    btn.setAttribute('tabindex', '-1');
    btn.addEventListener('click', () => {
      const input = btn.closest('.input-wrapper')?.querySelector('input');
      if (!input) return;
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
      btn.classList.toggle('is-visible', show);
    });
  });

  /* ── Password strength meter (on Password field) ───────────────────────────── */
  if (pwd1) {
    const meter = document.createElement('span');
    meter.className = 'password-strength';
    meter.setAttribute('aria-hidden', 'true');
    meter.innerHTML = '<span class="password-strength__bar"></span>';
    pwd1.closest('.form-group')?.append(meter);

    pwd1.addEventListener('input', () => {
      const v = pwd1.value;
      const score = [
        v.length >= 8,
        /[a-z]/.test(v) && /[A-Z]/.test(v),
        /\d/.test(v),
        /[^A-Za-z0-9]/.test(v),
      ].filter(Boolean).length;
      const bar = meter.firstElementChild;
      bar.style.width      = `${score * 25}%`;
      bar.dataset.strength = score >= 4 ? 'strong' : score >= 2 ? 'medium' : 'weak';
    });
  }

  /* ── Terms checkbox: hide error as soon as user checks it ───────────────────── */
  termsCheckbox?.addEventListener('change', () => {
    if (termsCheckbox.checked) {
      if (termsError) termsError.hidden = true;
      termsCheckbox.closest('label')?.classList.remove('checkbox-label--error');
    }
  });

  /* ── TAB ORDER ─────────────────────────────────────────────────────────────────
       Confirm Password  →Tab→  "I agree" checkbox  →Tab→  Create Account  →Tab→  stop
       Shift+Tab works in reverse.
  ──────────────────────────────────────────────────────────────────────────────── */

  /* 1. Confirm Password → terms checkbox */
  if (pwd2 && termsCheckbox) {
    pwd2.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !e.shiftKey) {
        e.preventDefault();
        termsCheckbox.focus();
      }
    });
  }

  /* 2. Terms checkbox → Create Account (forward) / Confirm Password (back) */
  if (termsCheckbox) {
    termsCheckbox.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !e.shiftKey && submitBtn) {
        e.preventDefault();
        submitBtn.focus();
      }
      if (e.key === 'Tab' && e.shiftKey && pwd2) {
        e.preventDefault();
        pwd2.focus();
      }
    });
  }

  /* 3. Create Account: Tab stops here / Shift+Tab goes back to terms */
  if (submitBtn) {
    submitBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && !e.shiftKey) {
        e.preventDefault();                   // nothing after Create Account
      }
      if (e.key === 'Tab' && e.shiftKey && termsCheckbox) {
        e.preventDefault();
        termsCheckbox.focus();
      }
    });
  }

  /* ── Form submit: require terms + block double-submit ───────────────────────── */
  signupForm.addEventListener('submit', (e) => {
    if (termsCheckbox && !termsCheckbox.checked) {
      e.preventDefault();
      if (termsError) termsError.hidden = false;
      termsCheckbox.closest('label')?.classList.add('checkbox-label--error');
      termsCheckbox.focus();
      return;
    }
    if (termsError) termsError.hidden = true;
    if (!submitBtn || !signupForm.checkValidity()) return;
    submitBtn.disabled = true;
    const lbl = submitBtn.querySelector('span:first-child');
    if (lbl) lbl.textContent = 'Creating your account…';
  });

}
