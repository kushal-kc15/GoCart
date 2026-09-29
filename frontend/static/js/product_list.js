const categoryStrip = document.getElementById("categoryStrip");
const previousButton = document.getElementById("categoryPrev");
const nextButton = document.getElementById("categoryNext");

if (categoryStrip && previousButton && nextButton) {
  previousButton.addEventListener("click", () => {
    categoryStrip.scrollBy({ left: -420, behavior: "smooth" });
  });

  nextButton.addEventListener("click", () => {
    categoryStrip.scrollBy({ left: 420, behavior: "smooth" });
  });
}
