const KEY = "grocery_products"; // same key as the product list page
const MAX = 5;                  // max images per product
const CATS = ["Fruits", "Vegetables", "Dairy", "Bakery", "Meat & Fish", "Beverages", "Snacks", "Staples"];
const UNITS = ["kg", "g", "L", "pc", "pack"];
const $ = (id) => document.getElementById(id);

let images = [], origs = [], sel = 0;       // cropped images, their originals, selected index
let cropIdx = -1, pendingOrig = "", cropper, cropModal; // cropIdx -1 = adding a new image

/* ---------- helpers ---------- */
function loadProducts() {
  try { const d = JSON.parse(localStorage.getItem(KEY)); if (Array.isArray(d)) return d; } catch (e) {}
  return [];
}
function toast(msg) {
  $("toastMsg").textContent = msg;
  bootstrap.Toast.getOrCreateInstance($("toast"), { delay: 2200 }).show();
}

/* ---------- quick info / preview ---------- */
function updatePreview() {
  const price = parseFloat($("price").value) || 0;
  const disc = parseFloat($("discount").value) || 0;
  const final = price * (1 - disc / 100);
  const active = $("status").checked;

  $("qName").textContent = $("name").value.trim() || "-";
  $("qCat").textContent = $("category").value || "-";
  $("qPrice").textContent = price > 0
    ? `Rs. ${final.toFixed(2)} / ${$("unit").value}` + (disc > 0 ? ` (${disc}% off)` : "") : "-";
  $("qStock").textContent = $("stock").value !== "" ? parseInt($("stock").value, 10) : "-";
  $("qStatus").textContent = active ? "In Stock" : "Out of Stock";
  $("statusLbl").textContent = active ? "In Stock" : "Out of Stock";
  $("qStatus").className = "status-badge " + (active ? "on" : "off");
  $("descCount").textContent = `${$("description").value.length}/300`;
}

/* ---------- image gallery ---------- */
function renderGallery() {
    const has = images.length > 0;

    $("pvImg").src = has ? images[sel] : "";
    $("pvImg").classList.toggle("d-none", !has);
    $("pvPlaceholder").classList.toggle("d-none", has);
    $("pvImageBox").classList.toggle("has-image", has);
    $("imgRow").classList.toggle("d-none", !has);

    // Update image count only if the element exists
    if ($("imgCount")) {
        $("imgCount").textContent = `${images.length}/${MAX} images`;
    }

    $("thumbs").innerHTML = images.map((src, i) =>
        `<button type="button" class="gc-thumb ${i === sel ? "active" : ""}" data-i="${i}">
            <img src="${src}" alt="">
        </button>`
    ).join("") +
    (images.length < MAX
        ? '<button type="button" class="gc-thumb add" id="thumbAdd"><i class="bi bi-plus-lg"></i></button>'
        : "");
}

function pickFile(file) {
  if (!file) return;
  if (!/^image\/(jpeg|png|webp)$/.test(file.type)) return toast("Only JPG, PNG or WEBP allowed");
  if (file.size > 5 * 1024 * 1024) return toast("Max image size is 5MB");
  if (images.length >= MAX) return toast(`Maximum ${MAX} images per product`);
  const fr = new FileReader();
  fr.onload = () => typeof Cropper === "undefined" ? addWithoutCrop(fr.result) : openCrop(fr.result, -1);
  fr.onerror = () => toast("Could not read this file");
  fr.readAsDataURL(file);
}
function openCrop(src, idx) {
  if (typeof Cropper === "undefined") return toast("Cropper.js did not load - check your internet connection");
  pendingOrig = src; cropIdx = idx;
  $("cropImg").src = src;
  cropModal.show();
}
// fallback if Cropper.js fails to load: resize and use as-is
function addWithoutCrop(src) {
  const img = new Image();
  img.onload = () => {
    const s = Math.min(1, 600 / Math.max(img.width, img.height));
    const c = document.createElement("canvas");
    c.width = img.width * s; c.height = img.height * s;
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    const out = c.toDataURL("image/jpeg", 0.85);
    images.push(out); origs.push(out); sel = images.length - 1; renderGallery();
    toast("Image added (cropping unavailable - Cropper.js did not load)");
  };
  img.onerror = () => toast("This image could not be opened");
  img.src = src;
}
function rotateSelected() {
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas");
    c.width = img.height; c.height = img.width;
    const ctx = c.getContext("2d");
    ctx.translate(c.width / 2, c.height / 2);
    ctx.rotate(Math.PI / 2);
    ctx.drawImage(img, -img.width / 2, -img.height / 2);
    images[sel] = origs[sel] = c.toDataURL("image/jpeg", 0.85);
    renderGallery();
  };
  img.src = images[sel];
}
function removeSelected() {
  images.splice(sel, 1); origs.splice(sel, 1);
  sel = Math.max(0, Math.min(sel, images.length - 1));
  renderGallery();
}

/* ---------- init ---------- */
document.addEventListener("DOMContentLoaded", () => {
  cropModal = new bootstrap.Modal($("cropModal"));
  $("category").innerHTML = '<option value="">Select category</option>' + CATS.map((c) => `<option>${c}</option>`).join("");
  $("unit").innerHTML = UNITS.map((u) => `<option>${u}</option>`).join("");
  renderGallery();
  updatePreview();

  ["name", "category", "unit", "price", "discount", "stock", "description"].forEach((id) =>
    $(id).addEventListener("input", updatePreview));
  $("status").addEventListener("change", updatePreview);

// Upload image through Product Preview
const previewFile = $("previewFile");
const previewBox = $("pvImageBox");

// Click to select image
previewBox.addEventListener("click", () => {
    previewFile.click();
});

// Select image from computer
previewFile.addEventListener("change", (e) => {
    const file = e.target.files[0];

    if (file) {
        pickFile(file);
    }

    previewFile.value = "";
});

// Drag image over preview
previewBox.addEventListener("dragover", (e) => {
    e.preventDefault();
    previewBox.classList.add("drag-over");
});

// Remove drag highlight
["dragleave", "dragend"].forEach((event) => {
    previewBox.addEventListener(event, () => {
        previewBox.classList.remove("drag-over");
    });
});

// Drop image into preview
previewBox.addEventListener("drop", (e) => {
    e.preventDefault();
    previewBox.classList.remove("drag-over");

    const file = e.dataTransfer.files[0];

    if (file) {
        pickFile(file);
    }
});

// Thumbnail selection and adding another image
$("thumbs").addEventListener("click", (e) => {
    const t = e.target.closest(".gc-thumb");

    if (!t) return;

    if (t.id === "thumbAdd") {
        return previewFile.click();
    }

    sel = parseInt(t.dataset.i, 10);
    renderGallery();
});

  // preview toolbar (acts on the selected image)
  $("imgCrop").addEventListener("click", () => openCrop(origs[sel] || images[sel], sel));
  $("imgRotate").addEventListener("click", rotateSelected);
  $("imgRemove").addEventListener("click", removeSelected);

  // cropper
  $("cropModal").addEventListener("shown.bs.modal", () => {
    cropper = new Cropper($("cropImg"), { aspectRatio: 1.6, viewMode: 1, autoCropArea: 1, background: false });
    document.querySelectorAll("#ratioGroup button").forEach((b, i) => b.classList.toggle("active", i === 0));
  });
  $("cropModal").addEventListener("hidden.bs.modal", () => { if (cropper) cropper.destroy(); cropper = null; });
  document.querySelectorAll("#ratioGroup button").forEach((b) => b.addEventListener("click", () => {
    cropper.setAspectRatio(parseFloat(b.dataset.ratio));
    document.querySelectorAll("#ratioGroup button").forEach((x) => x.classList.toggle("active", x === b));
  }));
  $("rotL").addEventListener("click", () => cropper.rotate(-90));
  $("rotR").addEventListener("click", () => cropper.rotate(90));
  $("zoomIn").addEventListener("click", () => cropper.zoom(0.1));
  $("zoomOut").addEventListener("click", () => cropper.zoom(-0.1));
  $("cropApply").addEventListener("click", () => {
    const c = cropper.getCroppedCanvas({ maxWidth: 600, maxHeight: 600, fillColor: "#fff", imageSmoothingQuality: "high" });
    const out = c.toDataURL("image/jpeg", 0.85);
    if (cropIdx === -1) { images.push(out); origs.push(pendingOrig); sel = images.length - 1; }
    else images[cropIdx] = out;
    renderGallery();
    cropModal.hide();
  });
  $("cropCancel").addEventListener("click", () => cropModal.hide());

  // success popup buttons
  $("sView").addEventListener("click", () => (window.location.href = "productmanagement.html"));
  $("sAnother").addEventListener("click", () => location.reload());

  // reset
  $("resetBtn").addEventListener("click", () => {
    $("addForm").reset();
    $("addForm").classList.remove("was-validated");
    $("previewFile").value = "";
    images = []; origs = []; sel = 0;
    renderGallery(); updatePreview();
  });

  // submit
  $("addForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const form = e.target, nameEl = $("name");
    const products = loadProducts(), name = nameEl.value.trim();

    nameEl.setCustomValidity("");
    $("nameErr").textContent = "Enter a product name (min 2 characters).";
    if (name && products.some((p) => p.name.toLowerCase() === name.toLowerCase())) {
      nameEl.setCustomValidity("duplicate");
      $("nameErr").textContent = "A product with this name already exists.";
    }
    if (!form.checkValidity()) return form.classList.add("was-validated");

    products.push({
      id: products.reduce((m, p) => Math.max(m, p.id), 0) + 1,
      name,
      category: $("category").value,
      unit: $("unit").value,
      price: parseFloat($("price").value),
      discount: parseFloat($("discount").value) || 0,
      stock: parseInt($("stock").value, 10),
      description: $("description").value.trim(),
      status: $("status").checked ? "in" : "out",
      image: images[0] || "",
      images: images.slice(),
      icon: "🛒",
    });

    try { localStorage.setItem(KEY, JSON.stringify(products)); }
    catch (err) { return toast("Storage full - use fewer or smaller images"); }

    const saved = products[products.length - 1];
    $("sName").textContent = saved.name;
    $("sInfo").textContent = `${saved.category} · Rs. ${saved.price.toFixed(2)} / ${saved.unit} · Stock: ${saved.stock}`;
    $("sImg").src = saved.image;
    $("sImg").classList.toggle("d-none", !saved.image);
    new bootstrap.Modal($("successModal")).show();
  });
});