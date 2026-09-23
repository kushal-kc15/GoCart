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

// Simple Product Search Suggestions
document.addEventListener("DOMContentLoaded", function () {
  const searchInput = document.getElementById("searchInput");
  const dropdown = document.getElementById("searchDropdown");
  const searchIcon = document.getElementById("searchIcon");
  const searchField = document.querySelector(".search-field");

  if (!searchInput || !dropdown) return;

  const products = [
    "Potato",
    "Potato chips slicer cutter",
    "Potato starch",
    "Potato peeler",
    "Potato chips",
    "Potato masher",
    "Potato biscuit",
    "Potato cutter",
    "Tuna Fish",
    "Baby shampoo",
    "Local Potato",
    "Chaaki Atta",
    "Sprite Cold Drink",
    "Instant Cup Noodles",
    "Fresh Tomato Sauce",
    "Organic Green Tea",
    "Fresh Mixed Fruits",
    "Fresh Farm Eggs",
    "Bakery Brown Bread"
  ];

  // Helper to bold the typed text
  function highlightMatch(text, query) {
    const reg = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi");
    return text.replace(reg, "<strong>$1</strong>");
  }

  // 2. Execute Search (Tab Title & Redirect)
  function doSearch(keyword) {
    const term = (keyword || searchInput.value).trim();
    if (!term) return; 

    dropdown.classList.remove("open");
    
    // Updates browser tab title: "Buy [product]..."
    const formatted = term.charAt(0).toUpperCase() + term.slice(1);
    document.title = `Buy ${formatted}...`;

    // Simulated server delay then redirect
    setTimeout(() => { 
      window.location.href = `search.html?q=${encodeURIComponent(term)}`;
    }, 600);
  }

  // 3. Live Suggestions on Typing
  searchInput.addEventListener("input", function () {
    const query = this.value.trim();

    if (!query) {
      dropdown.innerHTML = "";
      dropdown.classList.remove("open");
      return;
    }

    // Filter matching products
    const matches = products.filter(item => 
      item.toLowerCase().includes(query.toLowerCase())
    );

    if (matches.length === 0) {
      dropdown.innerHTML = `<div class="search-no-match">No results for "<strong>${query}</strong>"</div>`;
      dropdown.classList.add("open");
      return;
    }

    // Render simple suggestion items with search arrow
    dropdown.innerHTML = matches.slice(0, 8).map(name => `
      <div class="search-item" data-value="${name}">
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

  $("#searchWrap").on("submit", function (e) {
    e.preventDefault(); // stops the browser from navigating to search.html
  });

  // 6. Close when clicking outside
  document.addEventListener("click", function (e) {
    if (searchField && !searchField.contains(e.target)) {
      dropdown.classList.remove("open");
    } 
  });
});

// register
const authOverlay = document.getElementById("authOverlay");
const userChip = document.querySelector(".user-chip");

userChip?.addEventListener("click", (e) => {
  e.preventDefault();
  authOverlay.classList.add("open");
});

document.getElementById("authClose")?.addEventListener("click", () => {
  authOverlay.classList.remove("open");
});

authOverlay?.addEventListener("click", (e) => {
  if (e.target === authOverlay) authOverlay.classList.remove("open");
});

// Tab switching (Password / Phone Number) — purely visual for now
document.querySelectorAll(".auth-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".auth-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active"); 
  });
});

// Show/hide password
document.querySelector(".toggle-eye")?.addEventListener("click", function () {
  const input = this.previousElementSibling;
  input.type = input.type === "password" ? "text" : "password";
});

document.getElementById("loginForm")?.addEventListener("submit", (e) => {
  e.preventDefault();
  // BACKEND: send login request here
});

// ── Register modal 
const registerOverlay = document.getElementById("registerOverlay");

// Open register modal, close login modal
document.getElementById("switchToRegister")?.addEventListener("click", (e) => {
  e.preventDefault();
  authOverlay.classList.remove("open");
  registerOverlay.classList.add("open");
});

// Close register modal via × button
document.getElementById("registerClose")?.addEventListener("click", () => {
  registerOverlay.classList.remove("open");
});

// Close register modal when clicking outside the box (backdrop)
registerOverlay?.addEventListener("click", (e) => {
  if (e.target === registerOverlay) registerOverlay.classList.remove("open");
});

// Switch back to login modal from register modal
document.getElementById("switchToLogin")?.addEventListener("click", (e) => {
  e.preventDefault();
  registerOverlay.classList.remove("open");
  authOverlay.classList.add("open");
});

// Show / hide password toggles inside the register form
document.querySelectorAll(".reg-toggle-eye").forEach((btn) => {
  btn.addEventListener("click", function () {
    const input = this.previousElementSibling;
    input.type = input.type === "password" ? "text" : "password";
    this.textContent = input.type === "password" ? "👁" : "🙈";
  });
});

// Register form submit — with terms validation
(function () {
  const form       = document.getElementById("registerForm");
  const termsBox   = document.getElementById("regTerms");
  const termsRow   = document.getElementById("termsRow");
  const termsError = document.getElementById("regTermsError");


  termsBox?.addEventListener("change", () => {
    if (termsBox.checked) {
      termsError && (termsError.hidden = true);
      termsRow?.classList.remove("terms-row--error");
    }
  });

  form?.addEventListener("submit", (e) => {
    e.preventDefault();

    // Validate terms checkbox
    if (!termsBox?.checked) {
      termsError && (termsError.hidden = false);
      termsRow?.classList.remove("terms-row--error");
      void termsRow?.offsetWidth;                    
      termsRow?.classList.add("terms-row--error");
      termsBox?.focus();
      return;
    }

  
    termsError && (termsError.hidden = true);
    termsRow?.classList.remove("terms-row--error");

    // BACKEND: send signup / registration request here
  });
})();



