const categoryGrid = document.getElementById("categoryGrid");
if (categoryGrid) {
  const categorySection = categoryGrid.closest("section");
  const [catPrev, catNext] = categorySection.querySelectorAll(".slider-arrows button");
  if (catPrev) catPrev.addEventListener("click", () => categoryGrid.scrollBy({ left: -180, behavior: "smooth" }));
  if (catNext) catNext.addEventListener("click", () => categoryGrid.scrollBy({ left: 180, behavior: "smooth" }));
}
// ---------- Feature & Popular Products sliders ----------
function setupProductSlider(trackId, prevBtnId, nextBtnId) {
  const track = document.getElementById(trackId);
  const prevBtn = document.getElementById(prevBtnId);
  const nextBtn = document.getElementById(nextBtnId);

  if (!track || !prevBtn || !nextBtn) return;

  const cardWidth = 260;
  const gap = 20;
  const step = cardWidth + gap;

  let currentIndex = 0;

  function updateTrackPosition() {
    track.style.transform = `translateX(${-currentIndex * step}px)`;
  }

  nextBtn.addEventListener("click", () => {
    const totalCards = track.children.length;
    if (currentIndex < totalCards - 1) {
      currentIndex++;
      updateTrackPosition();
    }
  });

  prevBtn.addEventListener("click", () => {
    if (currentIndex > 0) {
      currentIndex--;
      updateTrackPosition();
    }
  });
}

setupProductSlider("featureTrack", "featurePrev", "featureNext");
setupProductSlider("popularTrack", "popularPrev", "popularNext");
