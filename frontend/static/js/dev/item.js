// Product detail page interactions.
// Add to Cart is sent in place by common.js and Buy Now submits a normal form
// (the quantity comes from #qtyInput for both).
// Wishlist hearts are sent in place too; the review form is a plain form (no JS needed).
// Review likes are not saved yet, so their buttons are disabled; toggleLike is kept for later.

// ---- Quantity selector (limited by stock) ----
(function () {
  var info = document.querySelector(".product-info");
  if (!info) return;

  var MAX_STOCK = parseInt(info.dataset.stock, 10) || 0;
  var qtyVal = document.getElementById("qtyVal");
  var minusBtn = document.getElementById("qtyMinus");
  var plusBtn = document.getElementById("qtyPlus");
  var note = document.getElementById("stockNote");
  var qty = 1;

  function renderQty() {
    qtyVal.textContent = qty;
    minusBtn.disabled = qty <= 1;
    plusBtn.disabled = qty >= MAX_STOCK;
    if (MAX_STOCK <= 0) {
      note.textContent = "Out of stock";
      note.classList.add("low");
      return;
    }
    if (qty >= MAX_STOCK) {
      note.textContent = "Maximum available quantity selected (" + MAX_STOCK + ")";
    } else if (MAX_STOCK <= 5) {
      note.textContent = "Only " + MAX_STOCK + " left in stock";
    } else {
      note.textContent = MAX_STOCK + " available";
    }
    note.classList.toggle("low", qty >= MAX_STOCK || MAX_STOCK <= 5);
  }

  var qtyInput = document.getElementById("qtyInput"); // hidden field on the add-to-cart form

  // Exposed for the inline onclick handlers in the template
  window.changeQty = function (delta) {
    var next = qty + delta;
    if (next > MAX_STOCK) return;
    qty = Math.max(1, next);
    if (qtyInput) qtyInput.value = qty;
    renderQty();
  };

  // After an in-place Add to Cart, go back to 1 (the page reload used to do this)
  document.addEventListener("ajax:success", function (event) {
    if (event.target.dataset.ajax !== "cart-add") return;
    qty = 1;
    if (qtyInput) qtyInput.value = qty;
    renderQty();
  });

  renderQty();
})();

// ---- Gallery: thumbnails + main image switching ----
(function () {
  var mainImg = document.getElementById("mainImageImg");
  var mainBox = document.getElementById("mainImage");
  var thumbs = [].slice.call(document.querySelectorAll(".thumb"));
  if (!mainImg || thumbs.length === 0) return;

  function showThumb(el) {
    thumbs.forEach(function (t) { t.classList.remove("active-thumb"); });
    el.classList.add("active-thumb");
    var full = el.dataset.full;
    mainBox.classList.add("fade"); // fade out
    setTimeout(function () {
      if (full) mainImg.src = full;
      mainBox.classList.remove("fade"); // fade in
    }, 200);
  }

  // Exposed for the inline onclick handlers in the template
  window.selectThumb = function (el) {
    showThumb(el);
  };

  // Click the main image to advance to the next thumbnail
  mainBox.addEventListener("click", function () {
    var cur = thumbs.findIndex(function (t) {
      return t.classList.contains("active-thumb");
    });
    showThumb(thumbs[(cur + 1) % thumbs.length]);
  });
})();

// ---- Related products row scroll ----
window.scrollRelated = function (dir) {
  var grid = document.getElementById("relatedGrid");
  if (grid) grid.scrollBy({ left: dir * 280, behavior: "smooth" });
};

// ---- Review like toggle (cosmetic only) ----
window.toggleLike = function (el, base) {
  var liked = el.classList.toggle("liked");
  el.innerHTML = "👍 " + (liked ? base + 1 : base) + " likes";
};
