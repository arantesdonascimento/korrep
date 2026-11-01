/* Welcome popup: appears shortly after the page loads and invites the visitor to subscribe.
   - SHOW_MODE "visit" (default): once per visit, i.e. once per browser session. A reload or a
     trip to the subscribe form and back does not show it again; a new visit does.
   - SHOW_MODE "always": on every page load.
   - Nothing is stored about the visitor beyond the current browser session, and nothing is sent anywhere.
   - Add ?welcome=1 to the address to see it again whenever you like (handy for testing).
   - Esc, the X, the "Később" button and a click on the dark backdrop all close it. */
(function () {
  "use strict";

  var root = document.getElementById("welcome");
  if (!root) return;

  var DELAY_MS = 900;       // how soon after load it appears
  var SHOW_MODE = "visit";  // "visit" = once per visit | "always" = on every page load
  var KEY = "korrepWelcomeShown";

  var panel = root.querySelector(".welcome-panel");
  var forced = /[?&]welcome=1(&|$)/.test(window.location.search);
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var lastFocus = null;

  function markShown() {
    try { window.sessionStorage.setItem(KEY, "1"); } catch (e) { /* storage blocked: it then shows on every load */ }
  }

  function shownThisVisit() {
    try { return window.sessionStorage.getItem(KEY) === "1"; } catch (e) { return false; }
  }

  function focusables() {
    return Array.prototype.slice.call(panel.querySelectorAll("a[href], button:not([disabled])"));
  }

  function open() {
    if (!root.hidden) return;
    lastFocus = document.activeElement;
    markShown();
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
    root.classList.remove("is-open");
    document.documentElement.classList.remove("welcome-open");
    window.setTimeout(function () {
      root.hidden = true;
      if (lastFocus && lastFocus.focus) lastFocus.focus({ preventScroll: true });
    }, reduced ? 0 : 350);
  }

  root.addEventListener("click", function (event) {
    // the subscribe button is a normal link: it just takes the visitor to the form
    if (event.target.closest("[data-welcome-close]")) close();
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

  if (forced || SHOW_MODE === "always" || !shownThisVisit()) {
    window.setTimeout(open, DELAY_MS);
  }
})();
