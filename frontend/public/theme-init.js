(function () {
  var t = null, p = null;
  try { t = localStorage.getItem("finlit-theme"); p = localStorage.getItem("finlit-plan"); } catch (e) {}
  if (!t) t = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  if (["basic", "bronze", "gold"].indexOf(p) < 0) p = "gold";
  document.documentElement.setAttribute("data-theme", t);
  document.documentElement.setAttribute("data-plan", p);
})();
