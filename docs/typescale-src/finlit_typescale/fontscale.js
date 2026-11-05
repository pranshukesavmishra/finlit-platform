/*! FinLit type scale: runtime snap. A stopgap until the source uses the --fs-* tokens.

    <script src="/fontscale.js"></script>      (in index.html, anywhere in <head>)

  Every px font-size in the site's own stylesheets is moved to the nearest step of the scale
  11 12 13 14 16 18 20 24 28 32 40. Each rule keeps its selector, its place in the cascade and its
  !important, so nothing else about the page changes. Route styles that load later (code-split CSS)
  are caught as they arrive. Left alone: 0px (text hidden on purpose), 44px and up (display headings),
  em / rem / % / clamp() values, other sites' stylesheets (fonts) and inline style attributes.
  Remove the tag after fontsize_codemod.py has been run on the source. */
(function () {
  "use strict";

  function snap(px) {
    if (px < 6 || px >= 44) return null;
    if (px <= 11) return 11;
    if (px <= 12) return 12;
    if (px <= 13) return 13;
    if (px <= 14.5) return 14;
    if (px <= 17) return 16;
    if (px <= 19) return 18;
    if (px <= 22) return 20;
    if (px <= 26) return 24;
    if (px <= 29) return 28;
    if (px <= 37) return 32;
    return 40;
  }

  var PX = /^\s*([\d.]+)px\s*$/;
  var changed = 0;

  function fixRule(rule) {
    var style = rule.style;
    if (style) {
      var m = PX.exec(style.getPropertyValue("font-size"));
      if (m) {
        var px = parseFloat(m[1]);
        var to = snap(px);
        if (to !== null && to !== px) {
          style.setProperty("font-size", to + "px", style.getPropertyPriority("font-size"));
          changed++;
        }
      }
    }
    var kids = rule.cssRules;
    if (kids) for (var i = 0; i < kids.length; i++) fixRule(kids[i]);
  }

  var done = typeof WeakSet === "function" ? new WeakSet() : null;

  function run() {
    var sheets = document.styleSheets;
    for (var i = 0; i < sheets.length; i++) {
      var sheet = sheets[i];
      if (done && done.has(sheet)) continue;
      if (sheet.href && sheet.href.indexOf(location.origin) !== 0) continue;
      var rules;
      try { rules = sheet.cssRules; } catch (e) { continue; }   // not loaded yet, or another origin
      if (!rules || !rules.length) continue;
      for (var j = 0; j < rules.length; j++) fixRule(rules[j]);
      if (done) done.add(sheet);
    }
  }

  // Chart labels drawn as <text font-size="10">: a CSS rule outranks the attribute, so one small sheet covers them.
  function svgSheet() {
    var groups = {};
    for (var t = 60; t < 440; t += 5) {               // 6px to 43.5px in half-pixel steps
      var px = t / 10, to = snap(px);
      if (to === null || to === px) continue;
      var v = String(px);
      (groups[to] = groups[to] || []).push('[font-size="' + v + '"]', '[font-size="' + v + 'px"]');
    }
    var css = "";
    for (var k in groups) css += "svg " + groups[k].join(", svg ") + "{font-size:" + k + "px}\n";
    try {
      var sheet = new CSSStyleSheet();
      sheet.replaceSync(css);
      document.adoptedStyleSheets = document.adoptedStyleSheets.concat([sheet]);
    } catch (e) {
      var el = document.createElement("style");
      el.textContent = css;
      (document.head || document.documentElement).appendChild(el);
    }
  }

  run();
  svgSheet();
  document.addEventListener("load", function (e) {
    if (e.target && e.target.tagName === "LINK") run();
  }, true);
  new MutationObserver(run).observe(document.head || document.documentElement, { childList: true });
  window.addEventListener("DOMContentLoaded", run);

  window.finlitFontScale = { snap: snap, changed: function () { return changed; }, rerun: run };
})();
