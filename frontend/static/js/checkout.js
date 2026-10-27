// Checkout page (checkoutpage.html): delivery or pick up, saved addresses, and the
// "Pin on map" / "Type my address" switch with its map.
// Prices come from the server in "checkout-data"; this file only swaps which one shows.
// Address lookups go to our /api/geocode/ views, never straight to Nominatim.
// Text from the map, the store or the server is always set with textContent, never innerHTML.
(function () {
  var data = JSON.parse(document.getElementById("checkout-data").textContent);
  var form = document.getElementById("checkout-form");

  function $(id) {
    return document.getElementById(id);
  }
  function show(id, yes) {
    var element = $(id);
    if (element) element.hidden = !yes;
  }

  var latInput = $("id_lat");
  var lngInput = $("id_lng");
  var addressInput = $("id_address_line");
  var landmarkInput = $("id_landmark");
  var phoneInput = $("id_phone");
  var landmarkTag = $("landmark-tag");
  var locText = $("loc-text");
  var mapError = $("map-err");
  var confirmButton = $("map-confirm");

  var KATHMANDU = [27.7172, 85.324];
  var store = data.store;
  var storeOnMap = store.lat !== null && store.lng !== null;
  var mapWorks = typeof L !== "undefined"; // false if Leaflet didn't load (offline)
  var map = null;
  var pin = null;
  var storeMarker = null;
  var lookupTimer = null;
  var lookupCount = 0;

  // "map" = pin on map, "type" = typed address. Back after a form error with a typed
  // address (or an error on it), start on "type". Without a working map, always "type".
  var how = "map";
  if (
    !mapWorks ||
    $("typed-fields").querySelector(".field-err") ||
    (addressInput.value.trim() && !latInput.value)
  ) {
    how = "type";
  }

  // Hints that only matter without JavaScript ("Only needed for home delivery:")
  document.querySelectorAll(".no-js-hint").forEach(function (hint) {
    hint.hidden = true;
  });

  function method() {
    var checked = form.querySelector('input[name="delivery_method"]:checked');
    return checked ? checked.value : "delivery";
  }

  function isNewAddress() {
    var checked = form.querySelector('input[name="address_id"]:checked');
    return !checked || checked.value === ""; // no saved addresses: always new
  }

  // ---- Show the parts for the chosen delivery service and address ----
  function update() {
    var pickup = method() === "pickup";
    var newAddress = !pickup && isNewAddress();
    var onMap = newAddress && how === "map";

    $("dp-title").textContent = pickup
      ? "Pick up location"
      : "Delivery location";
    show("pickup-info", pickup);
    show("delivery-info", !pickup);
    show("addr-switch", newAddress && mapWorks);
    show("map-search", onMap);
    show("map-hint", onMap);
    show("map-confirm", onMap);
    show("typed-fields", newAddress && how === "type");
    show("landmark-field", newAddress);
    show("save-field", newAddress);
    show("map-box", mapWorks && (onMap || (pickup && storeOnMap)));
    $("mode-map").setAttribute("aria-pressed", String(how === "map"));
    $("mode-type").setAttribute("aria-pressed", String(how === "type"));

    // The server's totals for this delivery service
    $("summary-shipping").textContent = data.totals[method()].shipping;
    $("summary-total").textContent = data.totals[method()].total;

    hideError();
    if (!$("map-box").hidden) showOnMap(pickup);
  }

  form
    .querySelectorAll('input[name="delivery_method"]')
    .forEach(function (radio) {
      radio.addEventListener("change", update);
    });
  form.querySelectorAll('input[name="address_id"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      // A saved address brings its own phone, "Add new address" the account's. Still editable.
      if (radio.dataset.phone) phoneInput.value = radio.dataset.phone;
      update();
    });
  });
  $("mode-map").addEventListener("click", function () {
    how = "map";
    update();
  });
  $("mode-type").addEventListener("click", function () {
    how = "type";
    update();
  });

  function showError(text) {
    mapError.textContent = text;
    mapError.hidden = false;
  }
  function hideError() {
    mapError.hidden = true;
  }

  // ---- The map ----
  function markerIcon(className, symbol, size, anchor, popupAnchor) {
    var shape = document.createElement("div");
    shape.className = className;
    var mark = document.createElement("span");
    mark.textContent = symbol;
    shape.appendChild(mark);
    return L.divIcon({
      className: "custom-map-pin",
      html: shape,
      iconSize: size,
      iconAnchor: anchor,
      popupAnchor: popupAnchor,
    });
  }

  function popupBox(title, text, help) {
    var box = document.createElement("div");
    var heading = document.createElement("b");
    heading.textContent = title;
    var line = document.createElement("div");
    line.textContent = text;
    box.appendChild(heading);
    box.appendChild(line);
    if (help) {
      var small = document.createElement("small");
      small.className = "popup-help";
      small.textContent = help;
      box.appendChild(small);
    }
    return box;
  }

  function pinPopup(text) {
    return popupBox("📍 Delivery Spot", text, "Tap map or drag pin to adjust");
  }

  function startMap() {
    if (map) return;
    // Start at the default (else newest) pinned saved address, else the store,
    // else central Kathmandu. There is no pin until the customer drops one.
    var start = KATHMANDU;
    if (data.addresses.length) {
      start = [Number(data.addresses[0].lat), Number(data.addresses[0].lng)];
    } else if (storeOnMap) {
      start = [store.lat, store.lng];
    }
    map = L.map("map").setView(start, 15);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    map.on("click", function (event) {
      if (method() === "delivery" && isNewAddress() && how === "map")
        placePin(event.latlng);
    });

    if (storeOnMap) {
      storeMarker = L.marker([store.lat, store.lng], {
        icon: markerIcon("pin-store", "🏪", [32, 32], [16, 16], [0, -16]),
        title: store.name,
      });
      storeMarker.bindPopup(popupBox(store.name, store.address));
    }
  }

  function showOnMap(pickup) {
    startMap();
    // A map drawn while hidden has the wrong size until told to measure again.
    map.invalidateSize();
    if (pickup) {
      if (pin) pin.remove();
      storeMarker.addTo(map);
      map.setView([store.lat, store.lng], 16);
      storeMarker.openPopup();
      locText.textContent =
        "Pick up location: " +
        store.name +
        " (" +
        Number(store.lat).toFixed(5) +
        ", " +
        Number(store.lng).toFixed(5) +
        ")";
    } else {
      if (storeMarker) storeMarker.remove();
      if (pin) {
        pin.addTo(map);
        map.panTo(pin.getLatLng());
      }
      showPinStatus();
    }
  }

  // The green line under the map: what to do next, or the confirmed location.
  function showPinStatus() {
    if (method() === "pickup") return; // the line shows the store then
    if (!pin) {
      locText.textContent = "";
    } else if (!latInput.value) {
      locText.textContent =
        "Drag the pin to your exact spot, then press Confirm this location.";
    } else {
      locText.textContent =
        "Delivery location: " +
        (addressInput.value.trim() || "Pinned location") +
        " (" +
        Number(latInput.value).toFixed(5) +
        ", " +
        Number(lngInput.value).toFixed(5) +
        ")";
    }
  }

  function placePin(latlng, zoom) {
    if (pin) {
      pin.setLatLng(latlng);
    } else {
      pin = L.marker(latlng, {
        icon: markerIcon("pin-delivery", "📍", [34, 34], [17, 34], [0, -32]),
        draggable: true,
        title: "Delivery location",
      }).addTo(map);
      pin.bindPopup(pinPopup("Selected point on street map"));
      pin.on("dragend", pinMoved);
    }
    if (zoom) {
      map.setView(latlng, zoom);
    } else if (!map.getBounds().contains(latlng)) {
      map.panTo(latlng);
    }
    pinMoved();
    pin.openPopup();
  }

  function pinMoved() {
    // A moved pin is not used until it is confirmed again.
    latInput.value = "";
    lngInput.value = "";
    confirmButton.disabled = false;
    hideError();
    showPinStatus();
    pin.setPopupContent(pinPopup("Selected point on street map"));
    // Ask for the address once the pin has stayed still for a second.
    // The count makes answers for an older spot be ignored.
    lookupCount += 1;
    clearTimeout(lookupTimer);
    lookupTimer = setTimeout(lookUpAddress, 1000);
  }

  function confirmLocation() {
    if (!pin) return;
    var spot = pin.getLatLng();
    latInput.value = spot.lat.toFixed(6);
    lngInput.value = spot.lng.toFixed(6);
    confirmButton.disabled = true;
    hideError();
    showPinStatus();
  }
  confirmButton.addEventListener("click", confirmLocation);

  // ---- Suggestions from the map for the address and landmark ----
  // Fill a field from the map only if it is empty or was filled by the map before.
  function suggest(input, text) {
    if (!text) return false;
    if (input.value.trim() && !input.dataset.fromMap) return false; // the customer's own words win
    input.value = input.maxLength > 0 ? text.slice(0, input.maxLength) : text;
    input.dataset.fromMap = "true";
    return true;
  }

  function showLandmarkTag(fromMap) {
    landmarkTag.hidden = false;
    landmarkTag.classList.toggle("is-custom", !fromMap);
    landmarkTag.textContent = fromMap
      ? "📍 Nearest landmark auto-filled (editable)"
      : "✏️ Custom landmark / instructions";
    if (fromMap) {
      landmarkInput.classList.add("highlight-auto");
      setTimeout(function () {
        landmarkInput.classList.remove("highlight-auto");
      }, 2000);
    }
  }

  addressInput.addEventListener("input", function () {
    delete addressInput.dataset.fromMap;
  });
  landmarkInput.addEventListener("input", function () {
    delete landmarkInput.dataset.fromMap;
    showLandmarkTag(false);
  });

  function lookUpAddress() {
    var thisLookup = lookupCount;
    var spot = pin.getLatLng();
    var url =
      data.urls.reverse +
      "?lat=" +
      spot.lat.toFixed(6) +
      "&lng=" +
      spot.lng.toFixed(6);
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (found) {
        if (!found || thisLookup !== lookupCount) return; // failed, or the pin has moved since
        suggest(addressInput, found.address);
        if (suggest(landmarkInput, found.landmark)) showLandmarkTag(true);
        pin.setPopupContent(
          pinPopup(
            found.landmark || found.address || "Selected point on street map",
          ),
        );
        showPinStatus();
      })
      .catch(function () {
        /* no suggestion: the customer can type it */
      });
  }

  // ---- Search and "Use my location" ----
  function search() {
    var text = $("map-q").value.trim();
    if (text.length < 3) {
      showError("Type at least 3 letters to search.");
      return;
    }
    hideError();
    locText.textContent = "Searching…";
    fetch(data.urls.search + "?q=" + encodeURIComponent(text), {
      headers: { Accept: "application/json" },
    })
      .then(function (response) {
        if (response.status === 429) throw new Error("busy");
        if (!response.ok) throw new Error("failed");
        return response.json();
      })
      .then(function (found) {
        if (!found.results.length) {
          showPinStatus();
          showError(
            "We couldn't find that place. Try a nearby chowk or landmark, or tap the map.",
          );
          return;
        }
        var place = found.results[0];
        placePin(L.latLng(place.lat, place.lng), 16);
      })
      .catch(function (error) {
        showPinStatus();
        showError(
          error.message === "busy"
            ? "Search is busy. Please try again in a moment."
            : "Search isn't working right now. Tap the map instead.",
        );
      });
  }
  $("map-go").addEventListener("click", search);
  $("map-q").addEventListener("keydown", function (event) {
    if (event.key === "Enter") {
      event.preventDefault(); // Enter here searches; it must not place the order
      search();
    }
  });

  $("map-locate").addEventListener("click", function () {
    if (!navigator.geolocation) {
      showError(
        "Your browser can't share its location. Search or tap the map instead.",
      );
      return;
    }
    hideError();
    locText.textContent = "Finding your location…";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        placePin(
          L.latLng(position.coords.latitude, position.coords.longitude),
          17,
        );
      },
      function () {
        showPinStatus();
        showError(
          "Location access was blocked. Search or tap the map instead.",
        );
      },
      { timeout: 10000, enableHighAccuracy: true },
    );
  });

  // ---- Place Order ----
  // Capture phase: this runs before common.js's double-submit guard, so a stopped
  // submit doesn't leave the Place Order button disabled.
  form.addEventListener(
    "submit",
    function (event) {
      if (method() !== "delivery" || !isNewAddress()) return;

      if (how === "type") {
        // A typed address goes without a map pin.
        latInput.value = "";
        lngInput.value = "";
        return;
      }

      var problem = "";
      if (!pin) {
        problem = "Drop a pin on the map, or switch to Type my address.";
      } else if (!latInput.value) {
        problem = "Press Confirm this location before placing your order.";
      }
      if (problem) {
        event.preventDefault();
        showError(problem);
        (pin ? confirmButton : $("map-q")).focus();
        return;
      }
      // The map found no street for this pin: the pin and landmark still guide the courier.
      if (!addressInput.value.trim()) {
        addressInput.value =
          "Pinned location (" + latInput.value + ", " + lngInput.value + ")";
      }
    },
    true,
  );

  update();

  // Back after a form error: show the pin that was confirmed before.
  if (
    latInput.value &&
    lngInput.value &&
    map &&
    method() === "delivery" &&
    isNewAddress() &&
    how === "map"
  ) {
    placePin(L.latLng(Number(latInput.value), Number(lngInput.value)), 16);
    confirmLocation();
  }
})();
