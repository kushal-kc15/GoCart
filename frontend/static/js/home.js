const newsletterForm = document.querySelector('.newsletter__form');
const newsletterMessage = document.querySelector('.newsletter__message');

newsletterForm?.addEventListener('submit', (event) => {
  event.preventDefault();

  if (!newsletterForm.checkValidity()) {
    newsletterForm.reportValidity();
    return;
  }

  const emailInput = newsletterForm.querySelector('input[type="email"]');
  if (!emailInput || !newsletterMessage) return;

  newsletterMessage.textContent = `You're on the list — fresh updates are heading to ${emailInput.value}.`;
  newsletterForm.reset();
});

const categoryGrid = document.querySelector('.category-grid');
categoryGrid?.addEventListener('keydown', (event) => {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;

  const cards = [...categoryGrid.querySelectorAll('.category-card')];
  const currentIndex = cards.indexOf(document.activeElement);
  if (currentIndex < 0) return;

  event.preventDefault();
  const direction = event.key === 'ArrowRight' ? 1 : -1;
  cards[(currentIndex + direction + cards.length) % cards.length].focus();
});
