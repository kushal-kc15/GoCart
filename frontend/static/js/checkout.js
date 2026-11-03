// Checkout page (checkoutpage.html): delivery or pick up with an interactive
// Leaflet map. Prices come from the server in "checkout-data"; this file only
// swaps which one shows.
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
  var cityInput = $("id_city"); // hidden; from the map lookup
  var areaInput = $("id_area"); // hidden; the area and town from the map lookup, e.g. "Pokhara"
  var addressInput = $("id_address_line");
  var landmarkInput = $("id_landmark");
  var phoneInput = $("id_phone");
  var landmarkTag = $("landmark-tag");
  var locText = $("loc-text");
  var mapError = $("map-err");

  var POKHARA = [28.2096, 83.9856];
  var store = data.store;
  var storeOnMap = store.lat !== null && store.lng !== null;
  var mapWorks = typeof L !== "undefined"; // false if Leaflet didn't load (offline)
  var map = null;
  var pin = null;
  var storeMarker = null;
  var lookupTimer = null;
  var lookupCount = 0;

  // Hints that only matter without JavaScript ("Only needed for home delivery:")
  document.querySelectorAll(".no-js-hint").forEach(function (hint) {
    hint.hidden = true;
  });

  function method() {
    var checked = form.querySelector('input[name="delivery_method"]:checked');
    return checked ? checked.value : "delivery";
  }

  // ---- Show the parts for the chosen delivery service ----
  function update() {
    var pickup = method() === "pickup";
    var delivery = !pickup;
    var hasPin = pin !== null && !!latInput.value;

    $("dp-title").textContent = pickup
      ? "Pick up location"
      : "Delivery location";
    show("pickup-info", pickup);
    show("delivery-info", delivery);
    show("map-search", delivery && mapWorks);
    show("map-hint", delivery && mapWorks && !hasPin);
    show("street-field", delivery);
    show("street-hint", delivery);
    show("landmark-field", delivery);
    show("map-box", mapWorks && (delivery || (pickup && storeOnMap)));

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
    // Start at Pokhara coordinates (or server default). No pin until the customer drops one.
    var start =
      data.center && data.center.lat && data.center.lng
        ? [Number(data.center.lat), Number(data.center.lng)]
        : POKHARA;

    map = L.map("map").setView(start, 15);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    map.on("click", function (event) {
      if (method() === "delivery") placePin(event.latlng);
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
    setTimeout(function () {
      if (map) map.invalidateSize();
    }, 250);
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
      show("map-hint", false);
    } else {
      if (storeMarker) storeMarker.remove();
      if (pin) {
        pin.addTo(map);
        map.panTo(pin.getLatLng());
      }
      showPinStatus();
    }
  }

  // The green line under the map: confirmed location summary.
  function showPinStatus() {
    if (method() === "pickup") return;
    if (!pin || !latInput.value) {
      locText.textContent = "";
      show("map-hint", true);
    } else {
      var street = addressInput ? addressInput.value.trim() : "";
      var where = street
        ? [street, cityInput.value].filter(Boolean).join(", ")
        : areaInput.value || (cityInput.value ? cityInput.value : "");
      var text = "Location pinned" + (where ? ": " + where : "");
      locText.textContent = text;
      show("map-hint", false);
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
    // Auto-confirm coordinates immediately on pin placement/movement
    var spot = pin.getLatLng();
    latInput.value = spot.lat.toFixed(6);
    lngInput.value = spot.lng.toFixed(6);
    hideError();
    showPinStatus();
    pin.setPopupContent(pinPopup("Selected point on street map"));

    // Reverse geocode to populate city, area, street and nearest landmark
    lookupCount += 1;
    clearTimeout(lookupTimer);
    lookupTimer = setTimeout(lookUpAddress, 500);
  }

  // ---- Suggestions from the map for the address and landmark ----
  // Fill a field from the map only if it is empty or was filled by the map before.
  function suggest(input, text) {
    if (!input) return false;
    if (input.value.trim() && !input.dataset.fromMap) return false; // the customer's own words win
    text = text || "";
    input.value = input.maxLength > 0 ? text.slice(0, input.maxLength) : text;
    if (text) {
      input.dataset.fromMap = "true";
    } else {
      delete input.dataset.fromMap;
    }
    return text !== "";
  }

  function showLandmarkTag(fromMap) {
    if (!landmarkTag) return;
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

  if (addressInput) {
    addressInput.addEventListener("input", function () {
      delete addressInput.dataset.fromMap;
      showPinStatus();
    });
  }
  if (landmarkInput) {
    landmarkInput.addEventListener("input", function () {
      delete landmarkInput.dataset.fromMap;
      showLandmarkTag(false);
      showPinStatus();
    });
  }

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
        if (!found || thisLookup !== lookupCount) return;

        // Auto-confirm coordinates
        latInput.value = spot.lat.toFixed(6);
        lngInput.value = spot.lng.toFixed(6);

        // Silently populate street in the background for order address construction
        suggest(addressInput, found.street);
        cityInput.value = (found.city || "").slice(0, 100);
        areaInput.value = (found.area || "").slice(0, 150);

        if (suggest(landmarkInput, found.landmark)) {
          showLandmarkTag(true);
        } else if (!landmarkInput.value && landmarkTag) {
          landmarkTag.hidden = true;
        }

        pin.setPopupContent(
          pinPopup(
            found.landmark || found.address || "Selected point on street map",
          ),
        );
        showPinStatus();
      })
      .catch(function () {
        /* keep existing location info */
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

    var searchUrl = data.urls.search + "?q=" + encodeURIComponent(text);
    if (map) {
      var bounds = map.getBounds();
      var vb = [
        bounds.getWest().toFixed(4),
        bounds.getNorth().toFixed(4),
        bounds.getEast().toFixed(4),
        bounds.getSouth().toFixed(4),
      ].join(",");
      searchUrl += "&viewbox=" + encodeURIComponent(vb);
    }

    fetch(searchUrl, {
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
      if (method() !== "delivery") return;

      var problem = "";
      if (!pin || !latInput.value) {
        problem = "Drop a pin on the map to set your delivery location.";
      }
      if (problem) {
        event.preventDefault();
        showError(problem);
        $("map-q").focus();
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
    method() === "delivery"
  ) {
    var postedCity = cityInput.value;
    var postedArea = areaInput.value;
    placePin(L.latLng(Number(latInput.value), Number(lngInput.value)), 16);
    cityInput.value = postedCity;
    areaInput.value = postedArea;
    showPinStatus();
  }
})();
