/* ==========================================================================
   GoCart — site JavaScript
   ========================================================================== */

// ── Helpers ─────────────────────────────────────────────────────────────────
const $  = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Announcement bar ──────────────────────────────────────────────────────────
const announcementBar = $('#announcement-bar');
$('#announcement-bar .announcement__close')?.addEventListener('click', () => {
  announcementBar?.remove();
});

// ── Sticky header shadow ──────────────────────────────────────────────────────
const header = $('#site-header');
if (header) {
  const onScroll = () => header.classList.toggle('scrolled', window.scrollY > 8);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

// ── Search overlay ────────────────────────────────────────────────────────────
const searchOverlay = $('#search-overlay');
const searchInput   = $('#site-search');
const searchClose   = $('#search-close');

function openSearch() {
  searchOverlay?.classList.add('is-open');
  searchOverlay?.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
  setTimeout(() => searchInput?.focus(), 80);
}

function closeSearch() {
  searchOverlay?.classList.remove('is-open');
  searchOverlay?.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

$$('.search-toggle').forEach(btn => btn.addEventListener('click', openSearch));
searchClose?.addEventListener('click', closeSearch);
searchOverlay?.addEventListener('click', e => {
  if (e.target === searchOverlay) closeSearch();
});

// ── Mobile drawer ─────────────────────────────────────────────────────────────
const hamburger      = $('#hamburger');
const mobileDrawer   = $('#mobile-drawer');
const drawerClose    = $('#drawer-close');
const drawerBackdrop = $('#drawer-backdrop');

function openDrawer() {
  mobileDrawer?.classList.add('is-open');
  mobileDrawer?.setAttribute('aria-hidden', 'false');
  drawerBackdrop?.classList.add('is-visible');
  hamburger?.classList.add('is-open');
  hamburger?.setAttribute('aria-expanded', 'true');
  document.body.style.overflow = 'hidden';
}

function closeDrawer() {
  mobileDrawer?.classList.remove('is-open');
  mobileDrawer?.setAttribute('aria-hidden', 'true');
  drawerBackdrop?.classList.remove('is-visible');
  hamburger?.classList.remove('is-open');
  hamburger?.setAttribute('aria-expanded', 'false');
  document.body.style.overflow = '';
}

hamburger?.addEventListener('click', openDrawer);
drawerClose?.addEventListener('click', closeDrawer);
drawerBackdrop?.addEventListener('click', closeDrawer);
$$('.mobile-drawer__nav a').forEach(a => a.addEventListener('click', closeDrawer));

// ── User account dropdown ─────────────────────────────────────────────────────
const userMenuBtn  = $('#user-menu-btn');
const userDropdown = $('#user-dropdown');

function closeUserMenu() {
  userDropdown?.classList.remove('is-open');
  userMenuBtn?.setAttribute('aria-expanded', 'false');
  userDropdown?.setAttribute('aria-hidden', 'true');
}

userMenuBtn?.addEventListener('click', e => {
  e.stopPropagation();
  const open = userDropdown?.classList.toggle('is-open');
  userMenuBtn.setAttribute('aria-expanded', String(open));
  userDropdown?.setAttribute('aria-hidden', String(!open));
});

document.addEventListener('click', e => {
  if (userDropdown && !$('#user-menu')?.contains(e.target)) {
    closeUserMenu();
  }
});

// ── Global Escape key ─────────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  closeSearch();
  closeDrawer();
  closeUserMenu();
});

// ── Password show / hide ──────────────────────────────────────────────────────
$$('.password-toggle').forEach(btn => {
  btn.addEventListener('click', () => {
    const id    = btn.dataset.target;
    const input = id ? document.getElementById(id) : btn.closest('.input-wrapper')?.querySelector('input');
    if (!input) return;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    btn.innerHTML = show
      ? `<svg style="width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
      : `<svg style="width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.8" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
  });
});

// ── Toast notifications ───────────────────────────────────────────────────────
function dismissToast(toast) {
  toast.style.opacity = '0';
  toast.style.transform = 'translateY(-10px) scale(0.96)';
  toast.style.transition = 'opacity 0.25s, transform 0.25s';
  setTimeout(() => toast.remove(), 260);
}

$$('.toast').forEach(toast => {
  toast.querySelector('.toast__close')?.addEventListener('click', () => dismissToast(toast));
  setTimeout(() => { if (toast.isConnected) dismissToast(toast); }, 5000);
});

// ── Scroll-reveal ─────────────────────────────────────────────────────────────
const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

$$('.reveal').forEach(el => revealObserver.observe(el));

// ── Newsletter form ───────────────────────────────────────────────────────────
const newsletterForm    = $('.newsletter__form');
const newsletterMessage = $('.newsletter__message');
newsletterForm?.addEventListener('submit', e => {
  e.preventDefault();
  const email = newsletterForm.querySelector('input[type="email"]')?.value;
  if (newsletterMessage) {
    newsletterMessage.textContent = `You're on the list — fresh updates heading to ${email}.`;
  }
  newsletterForm.reset();
});
