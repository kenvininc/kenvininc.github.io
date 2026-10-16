/* Kenvin Shop - control panel. Các form vẫn hoạt động khi tắt JavaScript. */
(function () {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  // Menu bên trái trên điện thoại
  var toggle = $("[data-sidebar-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = document.body.classList.toggle("sidebar-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (e) {
      if (document.body.classList.contains("sidebar-open") && !e.target.closest("#sidebar")) {
        document.body.classList.remove("sidebar-open");
        toggle.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") document.body.classList.remove("sidebar-open");
    });
  }

  // Hỏi xác nhận trước thao tác quan trọng
  $$("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    });
  });

  // Chống bấm gửi nhiều lần
  $$("form").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (e.defaultPrevented) return;
      if (form.dataset.submitting === "1") { e.preventDefault(); return; }
      if (form.target === "_blank") return;
      form.dataset.submitting = "1";
      var btn = e.submitter && e.submitter.matches("[data-submit-once]") ? e.submitter : $("[data-submit-once]", form);
      if (btn) btn.classList.add("is-loading");
    });
  });
  window.addEventListener("pageshow", function () {
    $$("form").forEach(function (f) { f.dataset.submitting = ""; });
    $$(".is-loading").forEach(function (b) { b.classList.remove("is-loading"); });
  });

  // Chọn nhiều dòng
  $$("[data-bulk-form]").forEach(function (form) {
    var all = $("[data-select-all]", form);
    var rows = $$("[data-row-check]", form);
    var submit = $("[data-bulk-submit]", form);
    var label = $("[data-bulk-count]", form);
    function update() {
      var n = rows.filter(function (r) { return r.checked; }).length;
      if (submit) submit.disabled = n === 0;
      if (label) label.textContent = n ? "Đã chọn " + n : "Chưa chọn mục nào";
      if (all) all.checked = n > 0 && n === rows.length;
    }
    if (all) all.addEventListener("change", function () { rows.forEach(function (r) { r.checked = all.checked; }); update(); });
    rows.forEach(function (r) { r.addEventListener("change", update); });
    update();
  });

  // Thêm dòng biến thể
  var addBtn = $("[data-formset-add]");
  if (addBtn) {
    var body = $("[data-formset-body]");
    var tpl = $("[data-formset-template]");
    var total = $("input[name$='-TOTAL_FORMS']");
    addBtn.addEventListener("click", function () {
      var idx = parseInt(total.value, 10);
      var html = tpl.innerHTML.replace(/__prefix__/g, String(idx));
      body.insertAdjacentHTML("beforeend", html);
      total.value = String(idx + 1);
      var row = body.lastElementChild;
      var active = $("input[name$='-is_active']", row);
      if (active) active.checked = true;
      var first = $("input[type=text]", row);
      if (first) first.focus();
    });
  }

  // Khoảng thời gian tùy chọn ở dashboard
  var range = $("[data-range-select]");
  if (range) {
    range.addEventListener("change", function () {
      var custom = range.value === "custom";
      $$("[data-custom-range]").forEach(function (el) { el.hidden = !custom; });
      if (!custom) range.form.submit();
    });
  }

  var f = $("[data-focus-on-load]");
  if (f) f.focus();
})();
