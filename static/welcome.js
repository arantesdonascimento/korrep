/* Welcome popup: appears shortly after the page loads and invites the visitor to subscribe.
   - After it is closed (or the button is used) it stays quiet for QUIET_DAYS days.
   - Add ?welcome=1 to the address to see it again whenever you like (handy for testing).
   - Esc, the X, the "Később" button and a click on the dark backdrop all close it. */
(function () {
  "use strict";

  var root = document.getElementById("welcome");
  if (!root) return;

  var DELAY_MS = 900;      // how soon after load it appears
  var QUIET_DAYS = 7;      // how long it stays away after being closed
  var KEY = "korrepWelcomeSeen";

  var panel = root.querySelector(".welcome-panel");
  var forced = /[?&]welcome=1(&|$)/.test(window.location.search);
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var lastFocus = null;

  function remember() {
    var now = String(Date.now());
    try { window.localStorage.setItem(KEY, now); return; } catch (e) { /* storage blocked */ }
    try { window.sessionStorage.setItem(KEY, now); } catch (e2) { /* nothing to do */ }
  }

  function recentlySeen() {
    var raw = null;
    try { raw = window.localStorage.getItem(KEY); } catch (e) { /* storage blocked */ }
    if (!raw) {
      try { raw = window.sessionStorage.getItem(KEY); } catch (e2) { /* nothing to do */ }
    }
    var t = parseInt(raw, 10);
    return !isNaN(t) && Date.now() - t < QUIET_DAYS * 86400000;
  }

  function focusables() {
    return Array.prototype.slice.call(panel.querySelectorAll("a[href], button:not([disabled])"));
  }

  function open() {
    if (!root.hidden) return;
    lastFocus = document.activeElement;
    root.hidden = false;
    document.documentElement.classList.add("welcome-open");
    // two frames, so the browser has painted the closed state and the transition runs
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () { root.classList.add("is-open"); });
    });
    var cta = root.querySelector("[data-welcome-cta]");
    (cta || panel).focus({ preventScroll: true });
  }

  function close() {
    if (root.hidden) return;
    remember();
    root.classList.remove("is-open");
    document.documentElement.classList.remove("welcome-open");
    window.setTimeout(function () {
      root.hidden = true;
      if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
    }, reduced ? 0 : 350);
  }

  root.addEventListener("click", function (event) {
    if (event.target.closest("[data-welcome-close]")) {
      close();
    } else if (event.target.closest("[data-welcome-cta]")) {
      remember(); // the link itself then takes the visitor to the form
    }
  });

  document.addEventListener("keydown", function (event) {
    if (root.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    // keep keyboard focus inside the dialog while it is open
    var items = focusables();
    if (!items.length) return;
    var first = items[0];
    var last = items[items.length - 1];
    if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  if (forced || !recentlySeen()) {
    window.setTimeout(open, DELAY_MS);
  }
})();
