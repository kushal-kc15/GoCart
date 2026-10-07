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

  // Furthest the track can move left so the last card ends at the right edge
  function getMaxShift() {
    const trackWidth = track.children.length * step - gap;
    return Math.max(0, trackWidth - track.parentElement.clientWidth);
  }

  function updateTrackPosition() {
    const shift = Math.min(currentIndex * step, getMaxShift());
    track.style.transform = `translateX(${-shift}px)`;
  }

  nextBtn.addEventListener("click", () => {
    if (currentIndex * step < getMaxShift()) {
      currentIndex++;
      updateTrackPosition();
    }
  });

  prevBtn.addEventListener("click", () => {
    // Window may have been resized since the last click, so keep the index in range
    currentIndex = Math.min(currentIndex, Math.ceil(getMaxShift() / step));
    if (currentIndex > 0) {
      currentIndex--;
      updateTrackPosition(); 
    }
  });
}

setupProductSlider("featureTrack", "featurePrev", "featureNext");
setupProductSlider("popularTrack", "popularPrev", "popularNext");

// Simple Product Search Suggestions
document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("searchInput");
  const dropdown = document.getElementById("searchDropdown");
  const searchIcon = document.getElementById("searchIcon");
  const searchField = document.querySelector(".search-field");

  if (!searchInput || !dropdown) return;

  const SUGGEST_URL = "/products/suggest/";
  const MIN_CHARS = 2;
  let debounceTimer = null;

  // Names come from the database and the query is typed by the user,
  // so escape both before putting them into innerHTML.
  function escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Helper to bold the typed text (both sides already escaped)
  function highlightMatch(text, query) {
    const safeText = escapeHtml(text);
    const safeQuery = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const reg = new RegExp(`(${safeQuery})`, "gi");
    return safeText.replace(reg, "<strong>$1</strong>");
  }

  function closeDropdown() {
    dropdown.innerHTML = "";
    dropdown.classList.remove("open");
  }

  // 1. Execute Search (Tab Title & Redirect)
  function doSearch(keyword) {
    const term = (keyword || searchInput.value).trim();
    if (!term) return;

    dropdown.classList.remove("open");

    // Updates browser tab title: "Buy [product]..."
    const formatted = term.charAt(0).toUpperCase() + term.slice(1);
    document.title = `Buy ${formatted}...`;

    window.location.href = `/products/?q=${encodeURIComponent(term)}`;
  }

  // 2. Show the suggestions returned by the server
  function renderSuggestions(names, query) {
    if (names.length === 0) {
      dropdown.innerHTML = `<div class="search-no-match">No results for "<strong>${escapeHtml(query)}</strong>"</div>`;
      dropdown.classList.add("open");
      return;
    }

    dropdown.innerHTML = names.map(name => `
      <div class="search-item" data-value="${escapeHtml(name)}">
        <span class="search-item__text">${highlightMatch(name, query)}</span>
        <span class="search-item__arrow" title="Search">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="7" y1="17" x2="17" y2="7"></line>
            <polyline points="7 7 17 7 17 17"></polyline>
          </svg>
        </span>
      </div>
    `).join("");

    dropdown.classList.add("open");
  }

  // 3. Live Suggestions on Typing (waits 250ms after the last key press)
  searchInput.addEventListener("input", function () {
    const query = this.value.trim();
    clearTimeout(debounceTimer);

    if (query.length < MIN_CHARS) {
      closeDropdown();
      return;
    }

    debounceTimer = setTimeout(function () {
      fetch(`${SUGGEST_URL}?q=${encodeURIComponent(query)}`)
        .then(response => response.json())
        .then(data => {
          // Ignore a late answer if the user has typed something else since
          if (searchInput.value.trim() !== query) return;
          renderSuggestions(data.results, query);
        })
        .catch(closeDropdown);
    }, 250);
  });

  // 4. Click a suggestion
  dropdown.addEventListener("click", function (e) {
    const item = e.target.closest(".search-item");
    if (!item) return;

    const val = item.getAttribute("data-value");
    searchInput.value = val;
    doSearch(val);
  });

  // 5. Click Search Icon or Press Enter
  if (searchIcon) { 
    searchIcon.addEventListener("click", () => doSearch());
  }

  searchInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      doSearch();
    }
  });

  // 6. Close when clicking outside
  document.addEventListener("click", function (e) {
    if (searchField && !searchField.contains(e.target)) {
      dropdown.classList.remove("open");
    } 
  });
});

// Auth is handled by the dedicated login/signup pages (accounts:login / accounts:signup),
// so the old on-home login/register modals and their scripts were removed.



