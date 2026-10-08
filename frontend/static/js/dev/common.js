// Shared behaviour for every dev page (loaded in base.html).

// ---- Flash messages: close button, and success/info hide themselves ----
// (errors stay until the user closes them). Used for the messages the server
// puts in the page and for the ones showMessage() adds below.
function setupMessage(message) {
  message.querySelector(".message-close").addEventListener("click", function () {
    message.remove();
  });

  if (message.classList.contains("success") || message.classList.contains("info")) {
    setTimeout(function () {
      message.classList.add("is-hiding");                     // fade out (CSS in base.html)
      setTimeout(function () { message.remove(); }, 300);
    }, 5000);
  }
}

document.querySelectorAll(".message").forEach(setupMessage);

// Show a message in the same floating box as the server's messages.
// level is "success", "info" or "error" (the CSS class of the message).
function showMessage(text, level) {
  if (!text) return;

  var box = document.querySelector(".messages");
  if (!box) return;

  // Keep at most 3 on screen, so quick clicks don't build a tall stack
  while (box.children.length >= 3) {
    box.firstElementChild.remove();
  }

  var message = document.createElement("div");
  message.className = "message " + level;

  // textContent, not innerHTML: the text contains product names
  var span = document.createElement("span");
  span.textContent = text;

  var close = document.createElement("button");
  close.type = "button";
  close.className = "message-close";
  close.setAttribute("aria-label", "Dismiss message");
  close.innerHTML = "&times;";

  message.append(span, close);
  box.appendChild(message);
  setupMessage(message);
}

// ---- Header badges: a number, hidden when it is 0 ----
// (the badges are always in the page, see base.html)
function setBadge(selector, count) {
  var badge = document.querySelector(selector);
  if (!badge) return;
  badge.textContent = count > 0 ? count : "";
  badge.hidden = !(count > 0);
}

// ---- In-place forms: <form data-ajax="..."> sends fetch instead of reloading the page ----
// Without JavaScript the form submits normally and the view redirects, so nothing breaks.
// With a fetch the view answers with JSON instead (it looks for the X-Requested-With
// header, see _json_reply in cart/views.py). This code does the parts every form shares:
//   lock the buttons -> send -> show the message -> update the header badges
// and then announces "ajax:success" on the form. Each page listens for that event
// and changes its own part of the page (the heart, a cart row, ...).
// This block must stay above the data-once block below, so it sees the submit first.
function sendInPlace(form) {
  // Lock the whole [data-ajax-lock] area (a cart row) so + and - can't overlap,
  // otherwise just this form. Buttons that were already disabled stay as they were.
  var area = form.closest("[data-ajax-lock]") || form;
  var buttons = Array.from(area.querySelectorAll("button:not(:disabled)"));
  var focused = document.activeElement;     // a disabled button loses the keyboard focus
  buttons.forEach(function (button) {
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  });

  function unlock() {
    buttons.forEach(function (button) {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    });
    if (focused && area.contains(focused)) focused.focus();
  }

  // Not form.action: forms with a field named "action" (the cart + / - and
  // wishlist forms) would give back that field instead of the URL.
  fetch(form.getAttribute("action"), {
    method: "POST",
    body: new FormData(form),     // includes the hidden csrfmiddlewaretoken, so CSRF just works
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then(function (response) {
      // A redirect we didn't ask for, e.g. the session ended and login_required sent us to login
      if (response.redirected) {
        window.location.href = response.url;
        return null;
      }
      // Anything that is not JSON is an error page (403 CSRF, 404, 500)
      var type = response.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") === -1) throw new Error("not JSON");
      return response.json();
    })
    .then(function (data) {
      if (!data) return;                              // we are leaving for the login page

      if (data.redirect) {                            // logged out: go to login, as the plain form does
        window.location.href = data.redirect;
        return;
      }

      unlock();                                       // before the page code runs, so it can disable buttons again
      showMessage(data.message, data.level);
      setBadge("[data-cart-badge]", data.cart_count);
      setBadge("[data-wishlist-badge]", data.wishlist_count);
      if (data.ok) {
        form.dispatchEvent(new CustomEvent("ajax:success", { bubbles: true, detail: data }));
      }
    })
    .catch(function () {
      unlock();
      showMessage("Something went wrong. Please refresh the page and try again.", "error");
    });
}

document.querySelectorAll("form[data-ajax]").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    // Buy Now goes to checkout, so it is a normal submit (the button has data-no-ajax)
    if (event.submitter && event.submitter.hasAttribute("data-no-ajax")) return;
    if (!window.fetch) return;

    event.preventDefault();
    sendInPlace(form);
  });
});

// ---- Wishlist hearts and the wishlist page's Remove button (data-ajax="wish-toggle") ----
document.addEventListener("ajax:success", function (event) {
  var form = event.target;
  if (form.dataset.ajax !== "wish-toggle") return;
  var data = event.detail;

  // Every heart for this product on the page: one product can be in two sliders
  document.querySelectorAll("form.wish-form").forEach(function (heart) {
    if (heart.querySelector('[name="product_id"]').value !== String(data.product_id)) return;

    // Fill or empty the heart, and make the next click do the opposite
    heart.querySelector(".wish").setAttribute("aria-pressed", data.saved ? "true" : "false");
    heart.querySelector('[name="action"]').value = data.saved ? "remove" : "add";
  });

  // On the wishlist page a product that is no longer saved leaves the page
  var card = form.closest("[data-remove-on-unsave]");
  if (card && !data.saved) removeWishlistCard(card);
});

function removeWishlistCard(card) {
  var grid = card.parentElement;
  var neighbour = card.nextElementSibling || card.previousElementSibling;
  card.remove();

  // Count the cards left on the page: the heading and the empty message follow that
  var left = grid.children.length;
  document.querySelector("[data-wishlist-count]").textContent = "(" + left + ")";
  document.querySelectorAll("[data-wishlist-filled]").forEach(function (part) { part.hidden = left === 0; });
  document.querySelectorAll("[data-wishlist-empty]").forEach(function (part) { part.hidden = left > 0; });

  // Keyboard focus goes to a neighbouring card's heart, or to the "Browse products" link
  var next = neighbour ? neighbour.querySelector(".wish") : document.querySelector("[data-wishlist-empty] a");
  if (next) next.focus();
}

// ---- Stop double submits: forms marked data-once only submit once ----
document.querySelectorAll("form[data-once]").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    // An in-place form (above) already sent this one with fetch
    if (event.defaultPrevented) return;

    if (form.dataset.submitted) {
      event.preventDefault();
      return;
    }
    form.dataset.submitted = "true";

    // The button that was clicked (a form can have two, e.g. Buy Now and
    // Add to Cart). Older browsers without event.submitter use the first one.
    var button = event.submitter || form.querySelector('[type="submit"]');
    if (button) {
      button.setAttribute("aria-busy", "true");
      // Disable a moment later, after the browser has read the form data,
      // so a submit button with a name still sends its value.
      setTimeout(function () { button.disabled = true; }, 0);
    }
  });
});

// The Back button can restore a page from the browser cache with the
// button still disabled. Re-enable only the buttons we disabled above
// (out-of-stock buttons were never busy, so they stay disabled).
window.addEventListener("pageshow", function (event) {
  if (!event.persisted) return;
  document.querySelectorAll("form[data-once]").forEach(function (form) {
    delete form.dataset.submitted;
  });
  document.querySelectorAll('button[aria-busy="true"]').forEach(function (button) {
    button.disabled = false;
    button.removeAttribute("aria-busy");
  });
});

// ---- Header account menu: close on outside click or Escape ----
// (it is a <details> element, so opening and closing already work without this)
var accountMenu = document.querySelector(".account-menu");
if (accountMenu) {
  document.addEventListener("click", function (event) {
    // Also close after clicking one of its links: "My Orders" only scrolls
    // when you are already on the profile page.
    if (!accountMenu.contains(event.target) || event.target.closest(".account-dropdown a")) {
      accountMenu.open = false;
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && accountMenu.open) {
      accountMenu.open = false;
      accountMenu.querySelector("summary").focus();
    }
  });
}
