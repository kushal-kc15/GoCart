/* search.js — reads ?q= from the URL, filters products, renders result cards */

// Product data. Keep names in sync with the `products` suggestion list in home2.js.
const PRODUCTS = [
  { name: "Tuna Fish",           category: "Meat, Egg and Fish",     img: "https://images.unsplash.com/photo-1607623814075-e51df1bdc82f?auto=format&fit=crop&w=400&q=80", unit: "by weight per Kg", price: 1200, inStock: true },
  { name: "Baby shampoo",        category: "Baby care",              img: "../static/images/baby product.jpg", unit: "", price: 1200, inStock: false },
  { name: "Local Potato",        category: "Vegetables and fruits",  img: "../static/images/potato.jpg",       unit: "by weight per Kg", price: 1200, inStock: true },
  { name: "Chaaki Atta",         category: "Atta and Rice",          img: "../static/images/aata.jpg",         unit: "by weight per Kg", price: 1200, inStock: true },
  { name: "Sprite Cold Drink",   category: "Alcohols and Beverages", img: "../static/images/sprite.jpg",       unit: "750 ml bottle",    price: 120,  inStock: true },
  { name: "Instant Cup Noodles", category: "Instant Food",           img: "../static/images/cup_noodles.jpg",  unit: "per cup 70g",      price: 110,  inStock: true },
  { name: "Fresh Tomato Sauce",  category: "Daily Essentials",       img: "../static/images/tomato_sauce.jpg", unit: "500g bottle",      price: 240,  inStock: true },
  { name: "Organic Green Tea",   category: "Beverages",              img: "../static/images/green_tea.jpg",    unit: "25 tea bags",      price: 350,  inStock: true }
];

const HEART = `<svg class="icon-svg" viewBox="0 0 24 24" fill="var(--coral)" stroke="var(--coral)" stroke-width="2"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z" /></svg>`;

function escapeHTML(str) {
  return String(str).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function cardHTML(p) {
  const disabled = p.inStock ? "" : "disabled";
  return `
    <div class="product-card">
      <div class="thumb">
        <span class="category-tag">${escapeHTML(p.category)}</span>
        <button class="wish" aria-label="Add to wishlist">${HEART}</button>
        <img src="${escapeHTML(p.img)}" alt="${escapeHTML(p.name)}">
      </div>
      <div class="info">
        <h3>${escapeHTML(p.name)}</h3>
        <p class="stock ${p.inStock ? "in" : "out"}">${p.inStock ? "In Stock" : "Out of Stock"}</p>
        <div class="price-row">
          <span>${escapeHTML(p.unit)}</span>
          <strong>rs. ${p.price}</strong>
        </div>
        <div class="actions">
          <button class="add" ${disabled}>Add to Cart</button>
          <button class="buy" ${disabled}>Buy Now</button>
        </div>
      </div>
    </div>`;
}

document.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const query = (params.get("q") || "").trim();

  const title = document.getElementById("resultsTitle");
  const count = document.getElementById("resultsCount");
  const grid = document.getElementById("resultsGrid");
  const input = document.getElementById("searchInput");

  const filterBar = document.getElementById("filterBar");
  const fMin = document.getElementById("filterMin");
  const fMax = document.getElementById("filterMax");
  const fSort = document.getElementById("filterSort");
  const fStock = document.getElementById("filterStock");
  const fReset = document.getElementById("filterReset");

  // Category dropdown. If the HTML has the older checkbox container
  // (id="categoryList") instead of the <select>, swap it for the dropdown.
  let fCategory = document.getElementById("filterCategory");
  if (!fCategory) {
    const holder = document.getElementById("categoryList");
    if (holder) {
      holder.className = "";
      holder.innerHTML = `<select id="filterCategory"><option value="">All categories</option></select>`;
      fCategory = document.getElementById("filterCategory");
    }
  }

  if (input) input.value = query;

  if (!query) {
    title.textContent = "Search products";
    grid.innerHTML = `<div class="results-empty"><p>Type something in the search bar to find products.</p></div>`;
    return;
  }

  document.title = `Buy ${query.charAt(0).toUpperCase() + query.slice(1)}...`;
  title.textContent = `Results for "${query}"`;

  // 1. Keyword match: every word must appear in name or category
  const words = query.toLowerCase().split(/\s+/);
  const matches = PRODUCTS.filter(p => {
    const haystack = `${p.name} ${p.category}`.toLowerCase();
    return words.every(w => haystack.includes(w));
  });

  // 2. Category dropdown: always lists every category
  const allCategories = [...new Set(PRODUCTS.map(p => p.category))];
  allCategories.forEach(cat => {
  const opt = document.createElement("option");
  opt.value = cat;
  opt.textContent = cat;
  fCategory.appendChild(opt);
});

  filterBar.hidden = false;

  // 3. Apply filters + sort, then render
  function render() {
    const cat = fCategory.value;
    const min = fMin.value === "" ? 0 : Number(fMin.value);
    const max = fMax.value === "" ? Infinity : Number(fMax.value);

    // Category chosen -> show that category from the whole catalog.
    // "All categories" -> only products that match the search keyword.
    const base = cat ? PRODUCTS.filter(p => p.category === cat) : matches;

    let list = base.filter(p =>
      p.price >= min && p.price <= max &&
      (!fStock.checked || p.inStock)
    );

    switch (fSort.value) {
      case "price-asc":  list = [...list].sort((a, b) => a.price - b.price); break;
      case "price-desc": list = [...list].sort((a, b) => b.price - a.price); break;
      case "name-asc":   list = [...list].sort((a, b) => a.name.localeCompare(b.name)); break;
    }

    if (cat) {
      count.textContent = `${list.length} product${list.length === 1 ? "" : "s"} in ${cat}`;
    } else if (matches.length === 0) {
      count.textContent = "";
    } else {
      count.textContent = list.length === matches.length
        ? `${matches.length} product${matches.length === 1 ? "" : "s"} found`
        : `${list.length} of ${matches.length} shown`;
    }

    if (list.length) {
      grid.innerHTML = list.map(cardHTML).join("");
    } else if (!cat && matches.length === 0) {
      grid.innerHTML = `
        <div class="results-empty">
          <p>No products found for "<strong>${escapeHTML(query)}</strong>".</p>
          <p class="hint">Check the spelling, try a shorter keyword, or pick a category on the left.</p>
        </div>`;
    } else {
      grid.innerHTML = `<div class="results-empty"><p>No products match these filters.</p></div>`;
    }
  }

 const fApply = document.getElementById("filterApply");
fApply.addEventListener("click", render);

[fMin, fMax].forEach(el =>
  el.addEventListener("keydown", e => { if (e.key === "Enter") render(); })
);

  fReset.addEventListener("click", () => {
    fCategory.value = "";
    fMin.value = "";
    fMax.value = "";
    fSort.value = "relevance";
    fStock.checked = false;
    render();
  });

  render();
});