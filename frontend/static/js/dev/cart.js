// "You may also like": the arrows scroll the row by one card (260px card + 20px gap).
// The section is not rendered when there is nothing to suggest.
const recsRow = document.getElementById("recsRow");
if (recsRow) {
  document.getElementById("recsPrev").addEventListener("click", () => recsRow.scrollBy({ left: -280, behavior: "smooth" }));
  document.getElementById("recsNext").addEventListener("click", () => recsRow.scrollBy({ left: 280, behavior: "smooth" }));
}

// ---- + / - and the trash button change the cart without reloading the page ----
// common.js sends the form and then announces "ajax:success" with the server's numbers
// (see update_quantity and remove_from_cart in cart/views.py). Without JavaScript the
// forms still post and the page reloads.
function plural(count, word) {
  return count + " " + word + (count === 1 ? "" : "s");
}

document.addEventListener("ajax:success", function (event) {
  const form = event.target;
  const kind = form.dataset.ajax;
  if (kind !== "cart-qty" && kind !== "cart-remove") return;

  const data = event.detail;
  const row = form.closest("[data-cart-row]");
  let nextFocus = null;

  if (kind === "cart-qty") {
    row.querySelector("[data-cart-qty]").textContent = data.quantity;
    row.querySelector("[data-cart-dec]").disabled = data.quantity <= 1;
  } else {
    // After removing a row, keyboard focus goes to a neighbouring row's trash button
    const neighbour = row.nextElementSibling || row.previousElementSibling;
    if (neighbour) nextFocus = neighbour.querySelector(".trash-btn");
    row.remove();
  }

  // Heading, "select all" label and the order summary (the server sends them ready to show)
  document.querySelector("[data-cart-items-label]").textContent = plural(data.cart_count, "item");
  document.querySelector("[data-cart-products-label]").textContent = "(" + plural(data.product_count, "product") + ")";
  document.querySelector("[data-cart-subtotal]").textContent = data.subtotal;
  document.querySelector("[data-cart-shipping]").textContent = data.shipping;
  document.querySelector("[data-cart-total]").textContent = data.grand_total;

  // Empty cart: hide the list and the checkout link, show the empty message
  const empty = data.product_count === 0;
  document.querySelectorAll("[data-cart-filled]").forEach(function (part) { part.hidden = empty; });
  document.querySelectorAll("[data-cart-empty]").forEach(function (part) { part.hidden = !empty; });
  if (empty) nextFocus = document.querySelector("[data-cart-empty] a");

  if (nextFocus) nextFocus.focus();
});
