const body = document.body;
const menuToggle = document.querySelector('.menu-toggle');
const navigation = document.querySelector('.primary-nav');
const searchToggle = document.querySelector('.search-toggle');
const searchPanel = document.querySelector('.search-panel');
const searchClose = document.querySelector('.search-close');
const searchInput = document.querySelector('#site-search');
const announcement = document.querySelector('.announcement');
const announcementClose = document.querySelector('.announcement__close');

menuToggle?.addEventListener('click', () => {
  const isOpen = body.classList.toggle('menu-open');
  menuToggle.setAttribute('aria-expanded', String(isOpen));
});

navigation?.addEventListener('click', (event) => {
  if (event.target.matches('a')) {
    body.classList.remove('menu-open');
    menuToggle?.setAttribute('aria-expanded', 'false');
  }
});

function setSearch(open) {
  searchPanel?.classList.toggle('is-open', open);
  searchPanel?.setAttribute('aria-hidden', String(!open));
  if (open) window.setTimeout(() => searchInput?.focus(), 250);
}

searchToggle?.addEventListener('click', () => setSearch(true));
searchClose?.addEventListener('click', () => setSearch(false));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    setSearch(false);
    body.classList.remove('menu-open');
    menuToggle?.setAttribute('aria-expanded', 'false');
  }
});

announcementClose?.addEventListener('click', () => announcement?.remove());

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.12 });

document.querySelectorAll('.reveal').forEach((element) => observer.observe(element));

const newsletterForm = document.querySelector('.newsletter__form');
const newsletterMessage = document.querySelector('.newsletter__message');
newsletterForm?.addEventListener('submit', (event) => {
  event.preventDefault();
  const emailInput = newsletterForm.querySelector('input[type="email"]');
  newsletterMessage.textContent = `You're on the list — fresh updates are heading to ${emailInput.value}.`;
  newsletterForm.reset();
});
