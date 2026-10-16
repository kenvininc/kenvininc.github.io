/* Kenvin Shop - tương tác phía khách. Trang vẫn dùng được khi tắt JavaScript. */
(function () {
  "use strict";
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ---------- Toast ---------- */
  function toast(message, type) {
    var wrap = $("[data-toasts]");
    if (!wrap) return;
    var el = document.createElement("div");
    el.className = "alert toast alert-" + (type || "success");
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.textContent = message;
    wrap.appendChild(el);
    setTimeout(function () { el.remove(); }, 4000);
  }

  /* ---------- Drawer (menu điện thoại, bộ lọc) ---------- */
  var lastFocus = null;
  function openDrawer(el, trigger) {
    lastFocus = trigger || document.activeElement;
    el.classList.add("open");
    el.setAttribute("aria-hidden", "false");
    document.body.classList.add("drawer-open");
    if (trigger) trigger.setAttribute("aria-expanded", "true");
    var focusable = el.querySelector("button, a, input");
    if (focusable) focusable.focus();
  }
  function closeDrawers() {
    $$(".drawer.open, .filters.open").forEach(function (el) {
      el.classList.remove("open");
      el.setAttribute("aria-hidden", "true");
    });
    document.body.classList.remove("drawer-open");
    $$("[data-drawer-open], [data-filter-open]").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
    if (lastFocus) { lastFocus.focus(); lastFocus = null; }
  }
  $$("[data-drawer-open]").forEach(function (btn) {
    btn.addEventListener("click", function () { openDrawer(document.getElementById(btn.getAttribute("data-drawer-open")), btn); });
  });
  $$("[data-filter-open]").forEach(function (btn) {
    btn.addEventListener("click", function () { openDrawer(document.getElementById("filters"), btn); });
  });
  $$("[data-drawer-close], [data-filter-close]").forEach(function (b) { b.addEventListener("click", closeDrawers); });

  // Accordion danh mục trên điện thoại: chạm để mở, không dùng hover.
  $$(".m-toggle").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var sub = document.getElementById(btn.getAttribute("aria-controls"));
      var open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      sub.hidden = open;
    });
  });

  /* ---------- Dropdown + mega menu (desktop/tablet) ---------- */
  function closeMenus(except) {
    $$("[data-dropdown].open").forEach(function (li) {
      if (li !== except) {
        li.classList.remove("open");
        var b = $(".nav-caret", li); if (b) b.setAttribute("aria-expanded", "false");
      }
    });
    var mega = $("[data-mega]");
    if (mega && mega !== except && mega.classList.contains("open")) {
      mega.classList.remove("open");
      $(".mega-trigger", mega).setAttribute("aria-expanded", "false");
    }
  }
  $$("[data-dropdown] .nav-caret").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var li = btn.closest("[data-dropdown]");
      var open = !li.classList.contains("open");
      closeMenus(li);
      li.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", String(open));
    });
  });

  var mega = $("[data-mega]");
  if (mega) {
    var trigger = $(".mega-trigger", mega);
    var hoverTimer;
    var canHover = window.matchMedia("(hover: hover)").matches;
    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = !mega.classList.contains("open");
      closeMenus(mega);
      mega.classList.toggle("open", open);
      trigger.setAttribute("aria-expanded", String(open));
    });
    if (canHover) {
      mega.addEventListener("mouseenter", function () {
        clearTimeout(hoverTimer);
        closeMenus(mega);
        mega.classList.add("open");
        trigger.setAttribute("aria-expanded", "true");
      });
      mega.addEventListener("mouseleave", function () {
        hoverTimer = setTimeout(function () {
          mega.classList.remove("open");
          trigger.setAttribute("aria-expanded", "false");
        }, 200);
      });
    }
    var tabs = $$("[data-mega-tab]", mega);
    function selectTab(tab) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).classList.toggle("active", on);
      });
    }
    tabs.forEach(function (tab, i) {
      tab.tabIndex = i === 0 ? 0 : -1;
      tab.addEventListener("click", function () { selectTab(tab); });
      tab.addEventListener("focus", function () { selectTab(tab); });
      if (canHover) tab.addEventListener("mouseenter", function () { selectTab(tab); });
      tab.addEventListener("keydown", function (e) {
        var idx = tabs.indexOf(tab);
        if (e.key === "ArrowDown") { e.preventDefault(); tabs[(idx + 1) % tabs.length].focus(); }
        if (e.key === "ArrowUp") { e.preventDefault(); tabs[(idx - 1 + tabs.length) % tabs.length].focus(); }
        if (e.key === "ArrowRight" || e.key === "Enter") {
          var first = $("a", document.getElementById(tab.getAttribute("aria-controls")));
          if (first && e.key === "ArrowRight") { e.preventDefault(); first.focus(); }
        }
      });
    });
  }
  document.addEventListener("click", function (e) {
    if (!e.target.closest("[data-dropdown]") && !e.target.closest("[data-mega]")) closeMenus(null);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var openMega = $("[data-mega].open");
      closeMenus(null);
      closeDrawers();
      if (openMega) $(".mega-trigger", openMega).focus();
    }
  });

  /* ---------- Banner trượt ---------- */
  $$("[data-carousel]").forEach(function (root) {
    var slides = $$(".hero-slide", root), dots = $$("[data-dot]", root), i = 0, timer;
    if (slides.length < 2) return;
    function show(n) {
      i = (n + slides.length) % slides.length;
      slides.forEach(function (s, k) {
        var on = k === i;
        s.classList.toggle("active", on);
        s.setAttribute("aria-hidden", String(!on));
        s.tabIndex = on ? 0 : -1;
      });
      dots.forEach(function (d, k) { if (k === i) d.setAttribute("aria-current", "true"); else d.removeAttribute("aria-current"); });
    }
    function start() {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      stop(); timer = setInterval(function () { show(i + 1); }, 5000);
    }
    function stop() { clearInterval(timer); }
    $("[data-prev]", root).addEventListener("click", function () { show(i - 1); start(); });
    $("[data-next]", root).addEventListener("click", function () { show(i + 1); start(); });
    dots.forEach(function (d) { d.addEventListener("click", function () { show(+d.getAttribute("data-dot")); start(); }); });
    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    var x0 = null;
    root.addEventListener("touchstart", function (e) { x0 = e.touches[0].clientX; stop(); }, { passive: true });
    root.addEventListener("touchend", function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0;
      if (Math.abs(dx) > 40) show(i + (dx < 0 ? 1 : -1));
      x0 = null; start();
    });
    start();
  });

  /* ---------- Số lượng ---------- */
  $$("[data-qty]").forEach(function (box) {
    var input = $("input", box);
    function step(d) {
      var min = +input.min || 0, max = +input.max || 999;
      var v = Math.min(max, Math.max(min, (parseInt(input.value, 10) || 0) + d));
      input.value = v;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    $("[data-qty-dec]", box).addEventListener("click", function () { step(-1); });
    $("[data-qty-inc]", box).addEventListener("click", function () { step(1); });
  });
  // Giỏ hàng: đổi số lượng thì tự lưu.
  $$("input[data-autosave]").forEach(function (input) {
    var t;
    input.addEventListener("change", function () {
      clearTimeout(t);
      t = setTimeout(function () { input.form.requestSubmit ? input.form.requestSubmit() : input.form.submit(); }, 600);
    });
  });

  /* ---------- Trang sản phẩm ---------- */
  var pdp = $("[data-pdp]");
  if (pdp) {
    var mainImg = $("[data-gallery-main]", pdp);
    var thumbs = $$("[data-gallery-thumb]", pdp);
    function showImage(src, alt, id) {
      if (!mainImg || !src) return;
      mainImg.src = src;
      if (alt) mainImg.alt = alt;
      thumbs.forEach(function (t) {
        if (t.getAttribute("data-image-id") === String(id)) t.setAttribute("aria-current", "true");
        else t.removeAttribute("aria-current");
      });
    }
    thumbs.forEach(function (t) {
      t.addEventListener("click", function () { showImage(t.getAttribute("data-src"), t.getAttribute("data-alt"), t.getAttribute("data-image-id")); });
    });

    var lowStock = +(document.body.getAttribute("data-low-stock") || 5);
    $$("input[name=variant_id][type=radio]", pdp).forEach(function (radio) {
      radio.addEventListener("change", function () {
        var d = radio.dataset, stock = +d.stock;
        $("[data-price]", pdp).textContent = d.price;
        $("[data-price]", pdp).classList.toggle("is-sale", !!d.compare);
        var cmp = $("[data-compare]", pdp), disc = $("[data-discount]", pdp);
        cmp.hidden = !d.compare; cmp.textContent = d.compare;
        disc.hidden = !d.discount; disc.textContent = d.discount ? "-" + d.discount + "%" : "";
        $("[data-sku]", pdp).textContent = d.sku;
        $("[data-variant-label]", pdp).textContent = d.label;
        var line = $("[data-stock-line]", pdp);
        line.className = "stock-line " + (stock <= 0 ? "out" : stock <= lowStock ? "low" : "in");
        line.textContent = stock <= 0 ? "Hết hàng" : stock <= lowStock ? "Chỉ còn " + stock + " sản phẩm" : "Còn hàng";
        var btn = $("[data-add-btn]", pdp);
        btn.disabled = stock <= 0;
        $("[data-add-text]", pdp).textContent = stock <= 0 ? "Hết hàng" : "Thêm vào giỏ";
        if (d.imageSrc) showImage(d.imageSrc, null, d.imageId);
        var url = new URL(window.location.href);
        url.searchParams.set("bien-the", radio.value);
        history.replaceState(null, "", url);
      });
    });
  }

  /* ---------- Thêm vào giỏ (AJAX, có fallback submit thường) ---------- */
  $$("form[data-add-to-cart]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.fetch) return;
      e.preventDefault();
      var btn = $("[data-add-btn]", form);
      if (btn.classList.contains("is-loading")) return;
      btn.classList.add("is-loading");
      btn.disabled = true;
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch", "Accept": "application/json" },
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(function (data) {
        toast(data.message, data.ok ? "success" : "error");
        if (typeof data.cart_count === "number") {
          $$("[data-cart-count]").forEach(function (el) { el.textContent = data.cart_count; el.setAttribute("data-count", data.cart_count); });
          $$("[data-cart-count-text]").forEach(function (el) { el.textContent = data.cart_count; });
        }
      }).catch(function () {
        toast("Không kết nối được, vui lòng thử lại.", "error");
      }).then(function () {
        btn.classList.remove("is-loading");
        var checked = $("input[name=variant_id]:checked", form);
        btn.disabled = checked ? +checked.dataset.stock <= 0 : false;
      });
    });
  });

  /* ---------- Chống bấm gửi form nhiều lần ---------- */
  $$("form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.hasAttribute("data-add-to-cart")) return;
      if (form.dataset.submitting === "1") { e.preventDefault(); return; }
      form.dataset.submitting = "1";
      var btn = $("[data-submit-once]", form);
      if (btn) { btn.classList.add("is-loading"); btn.setAttribute("aria-disabled", "true"); }
    });
  });
  window.addEventListener("pageshow", function () {
    $$("form").forEach(function (f) { f.dataset.submitting = ""; });
    $$("[data-submit-once]").forEach(function (b) { b.classList.remove("is-loading"); b.removeAttribute("aria-disabled"); });
  });

  /* ---------- Sắp xếp tự gửi ---------- */
  $$("form[data-autosubmit] select").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });

  /* ---------- Tabs thông tin sản phẩm ---------- */
  $$("[data-tabs]").forEach(function (root) {
    var tabs = $$("[role=tab]", root);
    function select(tab) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t); });
      t.addEventListener("keydown", function (e) {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          var n = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length];
          n.focus(); select(n);
        }
      });
    });
    if (tabs.length) select(tabs[0]);
  });

  var focusEl = $("[data-focus-on-load]");
  if (focusEl) focusEl.focus();
})();
