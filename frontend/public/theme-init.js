/*
 * Applies the saved theme and accent before the page paints (task 37.3), so
 * a dark theme never flashes white. A separate file because the Content
 * Security Policy allows no inline scripts. The account's saved choice
 * replaces these values once the user signs in.
 */
(function () {
  var root = document.documentElement;
  var theme = "system";
  var accent = "indigo";
  try {
    theme = JSON.parse(localStorage.getItem("savepass-theme") || '"system"');
    accent = JSON.parse(localStorage.getItem("savepass-accent") || '"indigo"');
  } catch (e) {
    /* storage unavailable: defaults */
  }
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  var dark = theme === "dark" || (theme === "system" && media && media.matches);
  root.classList.toggle("dark", !!dark);
  root.setAttribute("data-accent", accent);
})();
