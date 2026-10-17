(function () {
  var t = null, p = null, pv = null, d = null, root = document.documentElement;
  try { t = localStorage.getItem("finlit-theme"); p = localStorage.getItem("finlit-plan"); pv = localStorage.getItem("finlit-palette-vars"); d = localStorage.getItem("finlit-density"); } catch (e) {}
  if (!t) t = "light";
  if (["basic", "bronze", "gold"].indexOf(p) < 0) p = "gold";
  root.setAttribute("data-theme", t);
  root.setAttribute("data-plan", p);
  if (d === "compact") root.setAttribute("data-density", d);
  // The member's palette, saved as ready-made variables by the app, so the first paint is already in their colours.
  try {
    var v = pv && JSON.parse(pv);
    if (v && v.theme === t) { root.setAttribute("data-palette", v.id); for (var k in v.vars) root.style.setProperty(k, v.vars[k]); }
  } catch (e) {}
})();
