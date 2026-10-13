// Checkout page (dev/checkout.html): delivery method, saved addresses and the map pin.
// Prices come from the server in "checkout-data"; this file only shows them.
// Text from the map or the server is always set with textContent, never innerHTML.
(function () {
  var data = JSON.parse(document.getElementById("checkout-data").textContent);
  var form = document.querySelector(".checkout-wrap");
  var deliveryPanel = document.getElementById("delivery-panel");
  var pickupPanel = document.getElementById("pickup-panel");
  var newAddress = document.getElementById("new-address");
  var mapBox = document.getElementById("map-box");
  var statusText = document.getElementById("map-status");
  var searchInput = document.getElementById("map-search");
  var confirmButton = document.getElementById("map-confirm-btn");
  var latInput = document.getElementById("id_lat");
  var lngInput = document.getElementById("id_lng");
  var addressInput = document.getElementById("id_address_line");
  var landmarkInput = document.getElementById("id_landmark");

  var KATHMANDU = [27.7172, 85.324];
  var map = null;
  var pin = null;
  var lookupTimer = null;
  var lookupCount = 0;

  // Hints that only matter without JavaScript ("Only needed for home delivery.")
  document.querySelectorAll("[data-no-js]").forEach(function (hint) { hint.hidden = true; });

  // ---- Delivery or pickup: show the right panel and the server's totals ----
  function selectedMethod() {
    var checked = form.querySelector('input[name="delivery_method"]:checked');
    return checked ? checked.value : "delivery";
  }

  function showMethod() {
    var method = selectedMethod();
    deliveryPanel.hidden = method !== "delivery";
    pickupPanel.hidden = method !== "pickup";
    document.getElementById("summary-shipping").textContent = data.totals[method].shipping;
    document.getElementById("summary-total").textContent = data.totals[method].total;
    if (method === "delivery") showNewAddress();
  }

  // ---- A saved address, or "Add new address" (which opens the map) ----
  function isNewAddress() {
    var checked = form.querySelector('input[name="address_id"]:checked');
    return !checked || checked.value === "";  // no saved addresses: always new
  }

  function showNewAddress() {
    newAddress.hidden = !isNewAddress();
    if (newAddress.hidden) return;
    startMap();
    // A map drawn while hidden has the wrong size until told to measure again.
    if (map) map.invalidateSize();
  }

  form.querySelectorAll('input[name="delivery_method"]').forEach(function (radio) {
    radio.addEventListener("change", showMethod);
  });
  form.querySelectorAll('input[name="address_id"]').forEach(function (radio) {
    radio.addEventListener("change", showNewAddress);
  });

  // ---- The map ----
  function setStatus(text) {
    statusText.textContent = text;
  }

  function startMap() {
    // Already started, or Leaflet didn't load (offline): the typed address still works.
    if (map || typeof L === "undefined") return;
    mapBox.hidden = false;

    // Start at the newest pinned saved address, else central Kathmandu. No pin yet.
    var start = data.addresses.length ? [Number(data.addresses[0].lat), Number(data.addresses[0].lng)] : KATHMANDU;
    map = L.map("map").setView(start, 13);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    map.on("click", function (event) { placePin(event.latlng); });

    // Back after a form error: show the pin that was confirmed before.
    if (latInput.value && lngInput.value) {
      placePin(L.latLng(Number(latInput.value), Number(lngInput.value)), 16);
      confirmLocation();
    }
  }

  function placePin(latlng, zoom) {
    if (pin) {
      pin.setLatLng(latlng);
    } else {
      pin = L.marker(latlng, { draggable: true, title: "Delivery location" }).addTo(map);
      pin.on("dragend", pinMoved);
    }
    if (zoom) map.setView(latlng, zoom);
    pinMoved();
  }

  function pinMoved() {
    // A moved pin is not used until it is confirmed again.
    latInput.value = "";
    lngInput.value = "";
    confirmButton.disabled = false;
    setStatus("Drag the pin to your exact spot, then press Confirm this location.");
    // Ask for the address once the pin has stayed still for a second.
    clearTimeout(lookupTimer);
    lookupTimer = setTimeout(lookUpAddress, 1000);
  }

  function confirmLocation() {
    if (!pin) return;
    var spot = pin.getLatLng();
    latInput.value = spot.lat.toFixed(6);
    lngInput.value = spot.lng.toFixed(6);
    confirmButton.disabled = true;
    setStatus("Location confirmed. Check your street and landmark below.");
  }
  confirmButton.addEventListener("click", confirmLocation);

  // Fill a field from the map only if it is empty or was filled by the map before.
  function suggest(input, text) {
    if (!text) return;
    if (input.value.trim() && !input.dataset.fromMap) return;  // the customer's own words win
    input.value = text;
    input.dataset.fromMap = "true";
  }
  [addressInput, landmarkInput].forEach(function (input) {
    input.addEventListener("input", function () { delete input.dataset.fromMap; });
  });

  function lookUpAddress() {
    var spot = pin.getLatLng();
    var thisLookup = ++lookupCount;
    var url = data.urls.reverse + "?lat=" + spot.lat.toFixed(6) + "&lng=" + spot.lng.toFixed(6);
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (found) {
        if (!found || thisLookup !== lookupCount) return;  // failed, or the pin has moved since
        suggest(addressInput, found.address);
        suggest(landmarkInput, found.landmark);
      })
      .catch(function () { /* no suggestion: the customer types the address */ });
  }

  // ---- Search and "Use my location" ----
  function search() {
    var text = searchInput.value.trim();
    if (text.length < 3) {
      setStatus("Type at least 3 letters to search.");
      return;
    }
    setStatus("Searching…");
    fetch(data.urls.search + "?q=" + encodeURIComponent(text), { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (response.status === 429) throw new Error("busy");
        if (!response.ok) throw new Error("failed");
        return response.json();
      })
      .then(function (found) {
        if (!found.results.length) {
          setStatus("We couldn't find that place. Try a nearby chowk or landmark, or tap the map.");
          return;
        }
        var place = found.results[0];
        placePin(L.latLng(place.lat, place.lng), 16);
      })
      .catch(function (error) {
        setStatus(error.message === "busy"
          ? "Search is busy. Please try again in a moment."
          : "Search isn't working right now. Tap the map instead.");
      });
  }
  document.getElementById("map-search-btn").addEventListener("click", search);
  searchInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault();  // Enter here searches; it must not place the order
      search();
    }
  });

  document.getElementById("map-locate-btn").addEventListener("click", function () {
    if (!navigator.geolocation) {
      setStatus("Your browser can't share its location. Search or tap the map instead.");
      return;
    }
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      function (position) {
        placePin(L.latLng(position.coords.latitude, position.coords.longitude), 17);
      },
      function () { setStatus("Location access was blocked. Search or tap the map instead."); },
      { timeout: 10000, enableHighAccuracy: true }
    );
  });

  // A dropped pin that was never confirmed would be lost silently, so stop and ask.
  // Capture phase: this runs before common.js's double-submit guard, so a stopped
  // submit doesn't leave the Place Order button disabled.
  form.addEventListener("submit", function (event) {
    if (selectedMethod() === "delivery" && isNewAddress() && pin && !latInput.value) {
      event.preventDefault();
      setStatus("Press Confirm this location before placing your order.");
      confirmButton.focus();
    }
  }, true);

  showMethod();
})();
