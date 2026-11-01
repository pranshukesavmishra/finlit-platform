/* A first-visit brand introduction, independent of data fetching and React startup. */
(() => {
  const root = document.documentElement;
  const bootAt = performance.now();
  const key = 'finlit-introduction-v1';
  const reduced = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  let started = false, finishTimer, exitTimer, safetyTimer;
  let app, overlay, skip;
  const reset = () => {
    clearTimeout(finishTimer); clearTimeout(exitTimer); clearTimeout(safetyTimer);
    delete root.dataset.introduction;
    if (overlay) { overlay.hidden = true; delete overlay.dataset.phase; }
    if (app) app.inert = false;
    document.removeEventListener('keydown', onKey);
    started = false;
  };
  const finish = (immediate = false) => {
    if (!started) return;
    const restoreFocus = document.activeElement === skip;
    if (overlay && !immediate) overlay.dataset.phase = 'out';
    clearTimeout(finishTimer);
    exitTimer = setTimeout(() => {
      reset();
      if (restoreFocus) {
        const target = document.querySelector('#main h1') || document.querySelector('#main');
        if (target) { target.setAttribute('tabindex', '-1'); target.focus({ preventScroll: true }); }
      }
    }, immediate ? 0 : 380);
  };
  function onKey(event) { if (event.key === 'Escape') { event.preventDefault(); finish(true); } }
  const start = () => {
    if (started || reduced()) return;
    app = document.getElementById('root');
    overlay = document.querySelector('[data-finlit-intro]');
    skip = overlay?.querySelector('button');
    if (!overlay) { reset(); return; }
    started = true;
    // Schedule release before making the app inert: failure must never lock the page.
    safetyTimer = setTimeout(reset, 2800);
    finishTimer = setTimeout(() => finish(), 1250);
    overlay.hidden = false;
    root.dataset.introduction = 'on';
    if (app) app.inert = true;
    document.addEventListener('keydown', onKey);
    skip?.focus({ preventScroll: true });
    try { sessionStorage.setItem(key, 'seen'); } catch { /* a blocked store never blocks entry */ }
  };
  let seen = false;
  try { seen = sessionStorage.getItem(key) === 'seen'; } catch { /* first visit without storage */ }
  const params = new URLSearchParams(location.search);
  const basePath = document.currentScript?.src ? new URL('.', document.currentScript.src).pathname : '/';
  const home = location.pathname === basePath || location.pathname === basePath.replace(/\/$/, '');
  const shouldStart = home && !reduced() && params.get('intro') !== '0' && (!seen || params.get('intro') === '1');
  if (shouldStart) {
    root.dataset.introduction = 'on';
    try { sessionStorage.setItem(key, 'seen'); } catch { /* optional storage */ }
  }
  // Even if the document cannot finish loading, release the visual cover.
  setTimeout(() => { if (root.dataset.introduction === 'on') reset(); }, 3000);
  const ready = () => {
    overlay = document.querySelector('[data-finlit-intro]');
    overlay?.querySelector('button')?.addEventListener('click', () => finish(true));
    if (shouldStart && performance.now() - bootAt < 2000) start(); else reset();
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready, { once: true }); else ready();
  addEventListener('finlit:replay-introduction', start);
  window.matchMedia?.('(prefers-reduced-motion: reduce)').addEventListener?.('change', (e) => { if (e.matches) reset(); });
  addEventListener('pagehide', reset);
})();
