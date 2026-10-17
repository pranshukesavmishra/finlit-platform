// Keeps watchlists, saved screens and appearance in step with the signed-in account.
//  - On sign-in the saved copy is loaded (or, for a brand-new account, this browser's copy is uploaded once).
//  - Later changes are saved a moment after the member stops editing.
//  - On sign-out the personal lists are removed from this device; appearance stays.
import { useEffect, useRef } from "react";
import { useAuth } from "./auth";
import { DEMO } from "./demo";
import { loadState, savePortfolio, savePrefs, saveScreens, saveWatchlist } from "./account";
import { portfolio } from "./portfolio";
import { prefs } from "./prefs";
import { screens } from "./screens";
import { watch } from "./watchlist";
import { RANK } from "./ui";

const debounce = <A extends unknown[]>(fn: (...a: A) => void, ms = 900) => { let t = 0; return (...a: A) => { window.clearTimeout(t); t = window.setTimeout(() => fn(...a), ms); }; };

export function StateSync() {
  const { user, plan } = useAuth();
  const uid = user?.id ?? null;
  const last = useRef<string | null>(null);
  const silver = RANK[plan] >= RANK.silver;

  useEffect(() => {
    if (DEMO) return;
    if (!uid) {
      prefs.onSave(null); watch.onSave(null); screens.onSave(null); portfolio.onSave(null);
      if (last.current) { watch.reset(); screens.replace([]); portfolio.reset(); } // signed out: personal lists leave this device
      last.current = null;
      return;
    }
    let cancelled = false;
    const quiet = () => undefined;
    (async () => {
      let saved;
      try { saved = await loadState(); } catch { return; }
      if (cancelled) return;
      // Appearance: the account wins; a new account adopts this browser's choices.
      if (saved.prefs && Object.keys(saved.prefs).length) prefs.set(saved.prefs, true); else savePrefs(prefs.get()).catch(quiet);
      if (saved.screens?.length) screens.replace(saved.screens as never); else if (screens.get().length) saveScreens(screens.get()).catch(quiet);
      const wl = saved.watchlist;
      if (wl?.lists?.length) watch.replace({ lists: wl.lists, meta: wl.meta || {} });
      else if (silver && watch.total() > 0) saveWatchlist({ lists: watch.get().lists, meta: watch.get().meta }).catch(quiet);
      const pf = saved.portfolio?.holdings;
      if (pf?.length) portfolio.replace({ holdings: pf }); else if (silver && portfolio.get().holdings.length) savePortfolio(portfolio.get().holdings).catch(quiet);
      last.current = uid;
      portfolio.onSave(debounce((s) => { if (silver) savePortfolio(s.holdings).catch(quiet); }));
      prefs.onSave(debounce((p) => savePrefs(p).catch(quiet)));
      screens.onSave(debounce((s) => saveScreens(s).catch(quiet)));
      watch.onSave(debounce((s) => { if (silver) saveWatchlist({ lists: s.lists, meta: s.meta }).catch(quiet); }));
    })();
    return () => { cancelled = true; };
  }, [uid, silver]);
  return null;
}
