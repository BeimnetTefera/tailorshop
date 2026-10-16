(function () {
  "use strict";

  // ---- Bottom sheets (<dialog class="sheet">) ---------------------------------
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-open]");
    if (opener) {
      var dialog = document.getElementById(opener.dataset.open);
      if (dialog) { e.preventDefault(); dialog.showModal(); }
      return;
    }
    var closer = e.target.closest("[data-close]");
    if (closer) { e.preventDefault(); closer.closest("dialog").close(); return; }
    if (e.target.tagName === "DIALOG") e.target.close(); // tap on the backdrop
  });
  document.querySelectorAll("dialog[data-autoopen]").forEach(function (d) { d.showModal(); });

  // ---- Protected changes: "Are you sure?" (data-confirm) and the PIN (data-protect) ----
  // A protected form is held back, the PIN sheet checks the PIN with the server and gets
  // a short-lived token, then the form is sent again with that token attached.
  var pinSheet = document.getElementById("pin-sheet");
  var pinForm = pinSheet && pinSheet.querySelector("[data-pin-form]");
  var pendingForm = null;
  var pinCreating = false;

  function setPinMode(create) {
    pinCreating = create;
    pinSheet.querySelector("[data-pin-title]").textContent = create ? pinSheet.dataset.titleCreate : pinSheet.dataset.titleEnter;
    pinSheet.querySelector("[data-pin-intro]").textContent = create ? pinSheet.dataset.introCreate : pinSheet.dataset.introEnter;
    pinSheet.querySelector("[data-pin-enter]").hidden = create;
    pinSheet.querySelector("[data-pin-create]").hidden = !create;
    pinSheet.querySelector("[data-pin-forgot]").hidden = create;
    pinSheet.querySelector("[data-pin-error]").textContent = "";
    var first = pinSheet.querySelector(create ? "#pin-password" : "#pin-code");
    setTimeout(function () { first.focus(); }, 50);
  }

  function openPin(form, create) {
    pendingForm = form;
    pinForm.reset();
    if (!pinSheet.open) pinSheet.showModal();
    setPinMode(create || pinSheet.dataset.hasPin !== "1");
  }

  function sendPending(token) {
    var form = pendingForm;
    var field = form.querySelector("input[name=pin_token]");
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = "pin_token";
      form.appendChild(field);
    }
    field.value = token;
    form.dataset.pinOk = "1";
    pinSheet.close();
    if (form.requestSubmit) form.requestSubmit(); else form.submit();
  }

  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form === pinForm) return;
    if (form.dataset.confirm && !form.dataset.confirmed) {
      if (!window.confirm(form.dataset.confirm)) { e.preventDefault(); return; }
      form.dataset.confirmed = "1";
    }
    if (pinSheet && form.hasAttribute("data-protect") && !form.dataset.pinOk) {
      e.preventDefault();
      var sheet = form.closest("dialog");
      if (sheet && sheet !== pinSheet) sheet.close();
      openPin(form);
    }
  });

  if (pinForm) {
    pinSheet.querySelector("[data-pin-forgot]").addEventListener("click", function () { setPinMode(true); });
    document.querySelectorAll("[data-pin-change]").forEach(function (b) {
      b.addEventListener("click", function () { openPin(null, true); });
    });
    pinSheet.addEventListener("close", function () {
      // Cancelled: the next try asks again and the "Are you sure?" too.
      if (pendingForm && !pendingForm.dataset.pinOk) delete pendingForm.dataset.confirmed;
      pendingForm = null;
    });
    pinForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var error = pinSheet.querySelector("[data-pin-error]");
      var data = new FormData();
      data.append("csrfmiddlewaretoken", pinForm.querySelector("[name=csrfmiddlewaretoken]").value);
      if (pinCreating) {
        data.append("password", pinForm.querySelector("#pin-password").value);
        data.append("pin", pinForm.querySelector("#pin-new").value);
        data.append("pin2", pinForm.querySelector("#pin-again").value);
      } else {
        data.append("pin", pinForm.querySelector("#pin-code").value);
      }
      var button = pinForm.querySelector("button:not([type=button])");
      button.disabled = true;
      fetch(pinCreating ? pinSheet.dataset.setUrl : pinSheet.dataset.verifyUrl, {
        method: "POST", body: data, credentials: "same-origin", headers: { "X-Requested-With": "fetch" }
      }).then(function (r) { return r.json(); }).then(function (res) {
        button.disabled = false;
        if (res.ok) {
          pinSheet.dataset.hasPin = "1";
          if (pendingForm) { sendPending(res.token); return; }
          pinSheet.close();  // "Change PIN" with nothing waiting: just say it's saved
          var toast = document.createElement("div");
          toast.className = "toast";
          toast.textContent = res.message || "";
          var holder = document.querySelector(".toasts") || document.body.appendChild(document.createElement("div"));
          holder.className = "toasts";
          holder.appendChild(toast);
          setTimeout(function () { toast.classList.add("hide"); }, 3500);
          setTimeout(function () { toast.remove(); }, 4000);
        } else if (res.needs_pin) {
          setPinMode(true);
          error.textContent = res.error;
        } else {
          error.textContent = res.error;
          var input = pinForm.querySelector(pinCreating ? "#pin-new" : "#pin-code");
          input.value = "";
          input.focus();
        }
      }).catch(function () {
        button.disabled = false;
        error.textContent = pinSheet.dataset.errorNetwork;
      });
    });
  }

  // ---- Money chart: hover / focus tooltips on the bars -------------------------
  document.querySelectorAll("[data-chart-wrap]").forEach(function (wrap) {
    var tip = wrap.querySelector(".chart-tip");
    if (!tip) return;
    var show = function (el) {
      var mark = el.querySelector("i") || el;
      var r = mark.getBoundingClientRect(), w = wrap.getBoundingClientRect();
      tip.textContent = el.dataset.tip;
      tip.style.left = (r.left + r.width / 2 - w.left) + "px";
      tip.style.top = (r.top - w.top) + "px";
      tip.hidden = false;
    };
    var hide = function () { tip.hidden = true; };
    wrap.querySelectorAll("[data-tip]").forEach(function (el) {
      el.addEventListener("pointerenter", function () { show(el); });
      el.addEventListener("pointerleave", hide);
      el.addEventListener("focus", function () { show(el); });
      el.addEventListener("blur", hide);
    });
  });

  // ---- Toasts fade out ---------------------------------------------------------
  document.querySelectorAll(".toast").forEach(function (t) {
    setTimeout(function () { t.classList.add("hide"); }, 3500);
    setTimeout(function () { t.remove(); }, 4000);
  });

  // ---- Photo inputs: show the chosen image ------------------------------------
  document.querySelectorAll(".dropzone input[type=file]").forEach(function (input) {
    input.addEventListener("change", function () {
      var zone = input.closest(".dropzone");
      var text = zone.querySelector("[data-file-label]");
      var file = input.files && input.files[0];
      if (!file) return;
      if (text) text.textContent = input.files.length > 1 ? input.files.length + " " + (text.dataset.many || "") : file.name;
      var img = zone.querySelector("img");
      if (!img) { img = document.createElement("img"); img.alt = "Selected photo"; zone.insertBefore(img, zone.firstChild); }
      img.src = URL.createObjectURL(file);
    });
  });

  // ---- Update thread: show that a photo is attached -----------------------------
  document.querySelectorAll("input[data-attach]").forEach(function (input) {
    input.addEventListener("change", function () {
      input.closest(".attach").classList.toggle("has-file", !!(input.files && input.files.length));
    });
  });

  // ---- Style gallery: tap a thumbnail or swipe the big photo -------------------
  var gallery = document.querySelector("[data-gallery]");
  var mainImg = gallery && gallery.querySelector("[data-gallery-main]");
  var thumbs = gallery ? Array.prototype.slice.call(gallery.querySelectorAll("[data-gallery-thumb]")) : [];
  if (mainImg && thumbs.length) {
    var current = 0;
    var counter = gallery.querySelector("[data-gallery-count]");
    var reduceMotion = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    var showPhoto = function (i) {
      current = (i + thumbs.length) % thumbs.length;
      var src = thumbs[current].dataset.galleryThumb;
      thumbs.forEach(function (t, n) {
        t.classList.toggle("is-active", n === current);
        if (n === current) t.setAttribute("aria-current", "true"); else t.removeAttribute("aria-current");
      });
      if (counter) counter.textContent = (current + 1) + " / " + thumbs.length;
      mainImg.alt = mainImg.alt.replace(/photo \d+ of/, "photo " + (current + 1) + " of");
      if (reduceMotion) { mainImg.src = src; return; }
      mainImg.classList.add("is-swapping");
      setTimeout(function () { mainImg.src = src; mainImg.classList.remove("is-swapping"); }, 150);
    };
    thumbs.forEach(function (t, n) { t.addEventListener("click", function () { showPhoto(n); }); });
    var gx = 0, gy = 0;
    mainImg.addEventListener("touchstart", function (e) { gx = e.touches[0].clientX; gy = e.touches[0].clientY; }, { passive: true });
    mainImg.addEventListener("touchend", function (e) {
      var dx = e.changedTouches[0].clientX - gx, dy = e.changedTouches[0].clientY - gy;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) showPhoto(current + (dx < 0 ? 1 : -1));
    });
  }

  // ---- Style pages: previous / next slide in from the side ---------------------
  var stylePage = document.querySelector("[data-style-page]");
  if (stylePage) {
    var cameFrom = null;
    try { cameFrom = sessionStorage.getItem("styleNav"); sessionStorage.removeItem("styleNav"); } catch (err) {}
    if (cameFrom === "next" || cameFrom === "prev") stylePage.classList.add("enter-" + cameFrom);
    var go = function (link) {
      var dir = link.dataset.pager;
      try { sessionStorage.setItem("styleNav", dir); } catch (err) {}
      stylePage.classList.add("leave-" + dir);
      setTimeout(function () { window.location.href = link.href; }, 180);
    };
    document.querySelectorAll("[data-pager]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        go(link);
      });
    });
    window.addEventListener("pageshow", function (e) {
      // Coming back with the Back button can restore the faded-out page.
      if (e.persisted) stylePage.classList.remove("leave-next", "leave-prev");
    });
    document.addEventListener("keydown", function (e) {
      if (e.target.closest("input, textarea, select") || e.altKey || e.metaKey || e.ctrlKey) return;
      var link = document.querySelector('[data-pager="' + (e.key === "ArrowRight" ? "next" : e.key === "ArrowLeft" ? "prev" : "") + '"]');
      if (link) go(link);
    });
  }

  // ---- Swipe order cards: right = mark ready, left = edit ----------------------
  document.querySelectorAll(".swipe-card").forEach(function (card) {
    var startX = 0, startY = 0, dx = 0, tracking = false, moved = false;
    card.addEventListener("touchstart", function (e) {
      startX = e.touches[0].clientX; startY = e.touches[0].clientY; dx = 0; tracking = true; moved = false;
      card.classList.add("dragging");
    }, { passive: true });
    card.addEventListener("touchmove", function (e) {
      if (!tracking) return;
      dx = e.touches[0].clientX - startX;
      var dy = e.touches[0].clientY - startY;
      if (Math.abs(dy) > Math.abs(dx)) return;
      if (Math.abs(dx) > 8) moved = true;
      card.style.transform = "translateX(" + Math.max(-120, Math.min(120, dx)) + "px)";
    }, { passive: true });
    card.addEventListener("touchend", function () {
      tracking = false;
      card.classList.remove("dragging");
      card.style.transform = "";
      if (dx > 90 && card.dataset.right) {
        var form = document.getElementById(card.dataset.right);
        // requestSubmit (unlike submit) lets the PIN check step in.
        if (form && !form.querySelector("button[disabled]")) {
          if (form.requestSubmit) form.requestSubmit(); else form.submit();
        }
      } else if (dx < -90 && card.dataset.left) {
        window.location.href = card.dataset.left;
      }
    });
    card.addEventListener("click", function (e) { if (moved) { e.preventDefault(); moved = false; } }, true);
  });

  // ---- New order form ----------------------------------------------------------
  var total = document.getElementById("id_total_price");
  var deposit = document.getElementById("id_deposit");
  var remaining = document.querySelector("[data-remaining]");
  function updateRemaining() {
    if (!remaining || !total) return;
    var paid = parseFloat(remaining.dataset.paid || "0") + (deposit ? parseFloat(deposit.value || "0") : 0);
    var left = (parseFloat(total.value || "0") || 0) - (paid || 0);
    remaining.textContent = left.toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  [total, deposit].forEach(function (el) { if (el) el.addEventListener("input", updateRemaining); });
  updateRemaining();

  var styleMap = document.getElementById("style-categories");
  var styleSelect = document.getElementById("id_style");
  if (styleMap && styleSelect) {
    var map = JSON.parse(styleMap.textContent);
    styleSelect.addEventListener("change", function () {
      var cat = map[styleSelect.value];
      var radio = cat && document.querySelector('input[name="category"][value="' + cat + '"]');
      if (radio) radio.checked = true;
    });
  }

  var steps = document.querySelectorAll(".stepper a");
  if (steps.length && "IntersectionObserver" in window) {
    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        steps.forEach(function (s) { s.classList.toggle("active", s.getAttribute("href") === "#" + entry.target.id); });
      });
    }, { rootMargin: "-30% 0px -60% 0px" });
    document.querySelectorAll("[data-step]").forEach(function (sec) { observer.observe(sec); });
  }

  // ---- Style code suggestion follows the chosen category -----------------------
  var codeInput = document.querySelector("input[data-suggest]");
  if (codeInput) {
    var suggestions = JSON.parse(codeInput.dataset.suggest);
    var touched = false;
    codeInput.addEventListener("input", function () { touched = true; });
    document.querySelectorAll('input[name="category"]').forEach(function (r) {
      r.addEventListener("change", function () {
        if (!touched && suggestions[r.value]) codeInput.value = suggestions[r.value];
      });
    });
  }

  // ---- Record sale: live summary ----------------------------------------------
  var saleForm = document.querySelector("[data-sale-form]");
  if (saleForm) {
    var item = saleForm.querySelector("#id_item");
    var qty = saleForm.querySelector("#id_quantity");
    var amount = saleForm.querySelector("#id_amount");
    var amountEdited = amount.value !== "" && saleForm.dataset.bound === "1";
    amount.addEventListener("input", function () { amountEdited = true; });

    function selected() { return item.options[item.selectedIndex]; }
    function render() {
      var opt = selected();
      if (!opt || !opt.value) return;
      var stock = parseInt(opt.dataset.stock || "0", 10);
      var price = parseFloat(opt.dataset.price || "0");
      var n = Math.max(1, parseInt(qty.value || "1", 10));
      qty.max = stock;
      if (!amountEdited) amount.value = (price * n).toFixed(0);
      var fmt = function (v) { return Number(v || 0).toLocaleString("en-US"); };
      var words = saleForm.dataset;
      saleForm.querySelector("[data-sum-item]").textContent = opt.dataset.label;
      saleForm.querySelector("[data-sum-qty]").textContent = n;
      saleForm.querySelector("[data-sum-amount]").textContent = fmt(amount.value) + " " + words.currency;
      var after = stock - n;
      saleForm.querySelector("[data-sum-stock]").textContent = stock + " → " + (after < 0 ? words.notEnough : after + " " + words.available);
      saleForm.querySelector("[data-stock-note]").textContent = stock + " " + words.available;
    }
    saleForm.querySelectorAll("[data-step-qty]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var n = parseInt(qty.value || "1", 10) + parseInt(btn.dataset.stepQty, 10);
        var max = parseInt(selected().dataset.stock || "1", 10);
        qty.value = Math.max(1, Math.min(n, Math.max(max, 1)));
        render();
      });
    });
    item.addEventListener("change", function () { amountEdited = false; render(); });
    qty.addEventListener("input", render);
    amount.addEventListener("input", render);
    render();
  }
})();
