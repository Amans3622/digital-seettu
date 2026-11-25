/* Digital Seettu - shared front-end behaviour */
(function () {
  "use strict";

  var toastTimer = null;
  var money = new Intl.NumberFormat("en-LK", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });

  function formatMoney(value) {
    return "Rs. " + money.format(Number(value || 0));
  }

  function showToast(message, type) {
    var toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.classList.toggle("is-error", type === "error");
    toast.classList.add("is-visible");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(function () {
      toast.classList.remove("is-visible");
    }, 3800);
  }
  window.showToast = showToast;

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = text;
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (error) {
        reject(error);
      } finally {
        document.body.removeChild(area);
      }
    });
  }

  function updateText(selector, text) {
    document.querySelectorAll(selector).forEach(function (node) {
      node.textContent = text;
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    /* mobile navigation */
    var navToggle = document.querySelector("[data-nav-toggle]");
    var navLinks = document.querySelector("[data-nav-links]");
    if (navToggle && navLinks) {
      navToggle.addEventListener("click", function () {
        var open = navLinks.classList.toggle("is-open");
        navToggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
      navLinks.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", function () {
          navLinks.classList.remove("is-open");
          navToggle.setAttribute("aria-expanded", "false");
        });
      });
      document.addEventListener("click", function (event) {
        if (!navLinks.contains(event.target) && !navToggle.contains(event.target)) {
          navLinks.classList.remove("is-open");
          navToggle.setAttribute("aria-expanded", "false");
        }
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          navLinks.classList.remove("is-open");
          navToggle.setAttribute("aria-expanded", "false");
        }
      });
    }

    /* password visibility */
    document.querySelectorAll("[data-toggle-password]").forEach(function (button) {
      button.addEventListener("click", function () {
        var input = document.getElementById(button.dataset.togglePassword);
        if (!input) return;
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      });
    });

    /* flash messages */
    document.querySelectorAll(".flash").forEach(function (flash) {
      var close = function () {
        flash.classList.add("is-leaving");
        window.setTimeout(function () { flash.remove(); }, 320);
      };
      var button = flash.querySelector("[data-flash-close]");
      if (button) button.addEventListener("click", close);
      window.setTimeout(close, 7000);
    });

    /* copy invite codes */
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        copyText(button.dataset.copy).then(function () {
          showToast("Invite code copied: " + button.dataset.copy);
          var original = button.textContent;
          button.textContent = "Copied";
          window.setTimeout(function () { button.textContent = original; }, 1800);
        }).catch(function () {
          showToast("Could not copy. Select the code manually.", "error");
        });
      });
    });

    /* confirmation dialogs (non-AJAX forms) */
    document.querySelectorAll("form[data-confirm]").forEach(function (form) {
      if (form.hasAttribute("data-payment-form")) return;
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.dataset.confirm)) event.preventDefault();
      });
    });

    /* auto-number turn inputs */
    document.querySelectorAll("[data-autofill-turns]").forEach(function (button) {
      button.addEventListener("click", function () {
        var form = button.closest("form");
        if (!form) return;
        form.querySelectorAll(".turn-input").forEach(function (input, index) {
          input.value = index + 1;
        });
        showToast("Turn numbers filled. Save the order to apply.");
      });
    });

    /* print buttons */
    document.querySelectorAll("[data-print]").forEach(function (button) {
      button.addEventListener("click", function () { window.print(); });
    });

    /* registration validation */
    var validationForm = document.querySelector("form[data-validate]");
    if (validationForm) {
      validationForm.addEventListener("submit", function (event) {
        if (!validationForm.checkValidity()) {
          event.preventDefault();
          validationForm.reportValidity();
          return;
        }
        var main = validationForm.querySelector("[data-password-main]");
        var confirm = validationForm.querySelector("[data-password-confirm]");
        if (main && confirm && main.value !== confirm.value) {
          event.preventDefault();
          showToast(validationForm.dataset.matchMessage || "The two passwords do not match.", "error");
          confirm.focus();
        }
      });
    }

    /* ledger search + filters */
    var ledger = document.querySelector(".ledger-card");
    if (ledger) {
      var search = ledger.querySelector("[data-ledger-search]");
      var roundFilter = ledger.querySelector("[data-ledger-round]");
      var statusFilter = ledger.querySelector("[data-ledger-status]");
      var rows = Array.prototype.slice.call(ledger.querySelectorAll("tr[data-payment-id]"));
      var empty = ledger.querySelector("[data-ledger-empty]");

      var applyFilters = function () {
        var term = (search ? search.value : "").trim().toLowerCase();
        var roundValue = roundFilter ? roundFilter.value : "";
        var statusValue = statusFilter ? statusFilter.value : "";
        var visible = 0;
        rows.forEach(function (row) {
          var matches = true;
          if (term && (row.dataset.search || "").indexOf(term) === -1) matches = false;
          if (roundValue && row.dataset.round !== roundValue) matches = false;
          if (statusValue && row.dataset.status !== statusValue) matches = false;
          row.hidden = !matches;
          if (matches) visible += 1;
        });
        if (empty) empty.hidden = visible !== 0;
      };

      if (search) search.addEventListener("input", applyFilters);
      if (roundFilter) roundFilter.addEventListener("change", applyFilters);
      if (statusFilter) statusFilter.addEventListener("change", applyFilters);
    }

    /* live payment updates */
    document.querySelectorAll("[data-payment-form]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.fetch) return;
        event.preventDefault();
        if (form.dataset.confirm && !window.confirm(form.dataset.confirm)) return;

        var row = form.closest("[data-payment-id]");
        var roundRow = row ? document.querySelector('[data-round-row="' + row.dataset.roundId + '"]') : null;
        var button = form.querySelector("button[type=submit]");
        var originalLabel = button ? button.textContent : "";
        if (button) { button.disabled = true; button.textContent = "Saving..."; }

        fetch(form.action, {
          method: "POST",
          body: new FormData(form),
          headers: {
            "X-Requested-With": "fetch",
            "Accept": "application/json"
          },
          credentials: "same-origin"
        }).then(function (response) {
          return response.json();
        }).then(function (data) {
          if (!data.ok) {
            var failure = new Error(data.error || "Update failed");
            failure.seettu = true;
            throw failure;
          }

          if (row) {
            row.dataset.status = data.payment.status_label.toLowerCase();
            var status = row.querySelector(".js-pay-status");
            if (status) {
              status.className = "badge js-pay-status " + data.payment.badge_class;
              status.textContent = data.payment.status_label;
            }
            var dateCell = row.querySelector(".js-pay-date");
            if (dateCell) dateCell.textContent = data.payment.paid_date || "—";
            var methodCell = row.querySelector(".js-pay-method");
            if (methodCell) methodCell.textContent = data.payment.method_label || "—";
          }

          var roundComplete = data.round.status === "completed";
          var wasComplete = false;
          if (roundRow) {
            var roundStatus = roundRow.querySelector(".js-round-status");
            wasComplete = roundStatus ? roundStatus.textContent.trim() === "Complete" : false;
            var paid = roundRow.querySelector(".js-round-paid");
            if (paid) paid.textContent = data.round.paid_count + "/" + data.round.total_count;
            if (roundStatus) {
              roundStatus.className = "badge js-round-status " + (roundComplete ? "badge-complete" : "badge-pending");
              roundStatus.textContent = roundComplete ? "Complete" : "In progress";
            }
          }

          updateText(".js-collected", formatMoney(data.summary.collected));
          updateText(".js-pending", formatMoney(data.summary.pending));
          updateText(".js-overdue", formatMoney(data.summary.overdue));
          updateText(".js-paid-count", String(data.summary.paid_count));
          updateText(".js-total-count", String(data.summary.total_count));
          updateText(".js-rounds-completed", String(data.summary.rounds_completed));
          updateText(".js-overdue-count", String(data.summary.overdue_count));
          var pct = Math.max(0, Math.min(100, Math.round(data.summary.collected_pct)));
          updateText(".js-pct", pct + "%");
          document.querySelectorAll(".js-progress-bar").forEach(function (bar) {
            bar.style.width = pct + "%";
          });

          var paidNow = data.payment.status === "paid";

          if ((roundComplete && data.round.payout_ready) || (wasComplete && !roundComplete)) {
            showToast("Round updated. Refreshing so the payout controls stay in sync.");
            window.setTimeout(function () { window.location.reload(); }, 1400);
          } else {
            showToast(paidNow ? "Payment recorded as paid." : "Payment set back to pending.");
          }
        }).catch(function (error) {
          showToast(
            error && error.seettu
              ? error.message
              : "Could not update this payment. Please refresh and try again.",
            "error"
          );
        }).finally(function () {
          if (button) { button.disabled = false; button.textContent = originalLabel; }
        });
      });
    });
  });
})();
