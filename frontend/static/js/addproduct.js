const KEY = "grocery_products"; // same key as the product list page
const MAX = 8;                  // max images per product
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
  if ($("imgCount")) $("imgCount").textContent = `${images.length}/${MAX} images`;
  $("thumbs").innerHTML = images.map((src, i) =>
    `<button type="button" class="gc-thumb ${i === sel ? "active" : ""}" data-i="${i}" draggable="true"><img src="${src}" alt="" draggable="false">${i === 0 ? '<span class="gc-main">Main</span>' : ""}</button>`).join("") +
    (images.length < MAX ? '<button type="button" class="gc-thumb add" id="thumbAdd"><i class="bi bi-plus-lg"></i></button>' : "");
}

function readFile(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(fr.result);
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
}
function resize(src) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => {
      const s = Math.min(1, 600 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = img.width * s; c.height = img.height * s;
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      res(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = rej;
    img.src = src;
  });
}

// one or many files from the picker or from drag and drop
function pickFiles(list) {
  const files = [...list];
  if (!files.length) return;
  let ok = files.filter((f) => /^image\/(jpeg|png|webp)$/.test(f.type) && f.size <= 5 * 1024 * 1024);
  if (ok.length < files.length) toast(`${files.length - ok.length} file(s) skipped - JPG, PNG or WEBP up to 5MB only`);
  const room = MAX - images.length;
  if (!ok.length) return;
  if (room <= 0) return toast(`Maximum ${MAX} images per product`);
  if (ok.length > room) { ok = ok.slice(0, room); toast(`Only ${room} more image(s) allowed`); }

  if (ok.length === 1 && typeof Cropper !== "undefined") {
    readFile(ok[0]).then((src) => openCrop(src, -1)).catch(() => toast("Could not read this file"));
  } else {
    addMany(ok); // several files (or no Cropper): add directly, crop later with the Crop button
  }
}
async function addMany(files) {
  const outs = await Promise.all(files.map((f) => readFile(f).then(resize).catch(() => null)));
  const good = outs.filter(Boolean);
  if (!good.length) return toast("These images could not be opened");
  good.forEach((o) => { images.push(o); origs.push(o); });
  sel = images.length - good.length;
  renderGallery();
  toast(good.length > 1 ? `${good.length} images added - use Crop to adjust any of them` : "Image added");
}
function openCrop(src, idx) {
  if (typeof Cropper === "undefined") return toast("Cropper.js did not load - check your internet connection");
  pendingOrig = src; cropIdx = idx;
  $("cropImg").src = src;
  cropModal.show();
}

// drag and drop reordering: the first image is the main image
function moveImage(from, to) {
  if (from === to || from < 0 || to < 0) return;
  const [img] = images.splice(from, 1), [org] = origs.splice(from, 1);
  images.splice(to, 0, img); origs.splice(to, 0, org);
  sel = to;
  renderGallery();
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

  // upload: works whether the hidden input is id="previewFile" or id="file"
  const fileInput = $("previewFile") || $("file");
  fileInput.multiple = true;                      // allow selecting several images
  const openPicker = () => fileInput.click();
  fileInput.addEventListener("change", (e) => { pickFiles(e.target.files); e.target.value = ""; });

  // optional upload box inside the form (only if it exists in your HTML)
  const drop = $("drop");
  if (drop) {
    drop.addEventListener("click", openPicker);
    ["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", (e) => pickFiles(e.dataTransfer.files));
  }

  // big preview: click to upload (when empty), drop files, or drop a dragged thumbnail to make it main
  let dragFrom = -1;
  const box = $("pvImageBox");
  box.addEventListener("click", () => { if (!images.length) openPicker(); });
  box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drag-over"); });
  ["dragleave", "dragend"].forEach((ev) => box.addEventListener(ev, () => box.classList.remove("drag-over")));
  box.addEventListener("drop", (e) => {
    e.preventDefault();
    box.classList.remove("drag-over");
    if (dragFrom >= 0) { moveImage(dragFrom, 0); dragFrom = -1; }
    else if (e.dataTransfer.files.length) pickFiles(e.dataTransfer.files);
  });

  // thumbnails: select, add more (+), drag to reorder
  const thumbs = $("thumbs");
  thumbs.addEventListener("click", (e) => {
    const t = e.target.closest(".gc-thumb");
    if (!t) return;
    if (t.id === "thumbAdd") return openPicker();
    sel = parseInt(t.dataset.i, 10);
    renderGallery();
  });
  thumbs.addEventListener("dragstart", (e) => {
    const t = e.target.closest(".gc-thumb[data-i]");
    if (!t) return;
    dragFrom = parseInt(t.dataset.i, 10);
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", String(dragFrom));
    t.classList.add("dragging");
  });
  thumbs.addEventListener("dragover", (e) => {
    if (dragFrom < 0) return;
    e.preventDefault();
    thumbs.querySelectorAll(".dropping").forEach((x) => x.classList.remove("dropping"));
    const t = e.target.closest(".gc-thumb[data-i]");
    if (t) t.classList.add("dropping");
  });
  thumbs.addEventListener("drop", (e) => {
    e.preventDefault();
    const t = e.target.closest(".gc-thumb[data-i]");
    if (t && dragFrom >= 0) moveImage(dragFrom, parseInt(t.dataset.i, 10));
    dragFrom = -1;
  });
  thumbs.addEventListener("dragend", () => { dragFrom = -1; renderGallery(); });

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
    fileInput.value = "";
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