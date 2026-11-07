import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { UIProvider } from "./lib/ui";
import { AuthProvider } from "./lib/auth";
import { StateSync } from "./lib/sync";
import "@fontsource-variable/inter/wght.css";
import "@fontsource-variable/source-serif-4/wght.css";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans/latin-700.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import "@fontsource/ibm-plex-mono/latin-500.css";
import "@fontsource/ibm-plex-mono/latin-600.css";
import "./styles/typescale.css";
import "./styles/finlit.css";
import "./styles/site.css";
import "./styles/stock2.css";
import "./styles/ownership.css";
import "./styles/tools.css";
import "./styles/charthelp.css";
import "./styles/premium.css";
import "./styles/account.css";
import "./styles/human-pages.css";
import "./styles/theme.css";
import "./styles/depth3d.css";
import "./styles/leadership.css";
import "./styles/prism.css";
import "./styles/pagefaqs.css";
import "./styles/luxe.css";
import "./styles/headerlinks.css";
import "./styles/design-system.css";
import { installDemo } from "./lib/demo";
import { installResilience } from "./lib/resilience";
import { installSvgTextFit } from "./lib/svgText";
// Loaded last so these (sidebar, earnings dialog, opaque overlays) win over the page styles above. Kept apart from the style list so a team change there never collides with it.
import "./styles/sidebar.css";
import "./styles/earnings.css";
import "./styles/calm.css";
import "./styles/chartzoom.css";
import "./styles/overlay.css";
import { purgeLegacy } from "./lib/persist";

installDemo();
installResilience();
installSvgTextFit();
// Layout/behaviour flags written by releases before lib/persist.ts (raw, unversioned): drop them so stale values cannot reshape this release.
purgeLegacy(["finlit-side", "finlit-side-groups", "finlit-dash-open", "finlit-etf-cols-v2", "finlit-mf-cols-v4"], ["finlit.side."]);

const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <ErrorBoundary>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
        <AuthProvider>
          <UIProvider>
            <StateSync />
            <App />
          </UIProvider>
        </AuthProvider>
      </BrowserRouter>
      </ErrorBoundary>
    </QueryClientProvider>
  </StrictMode>,
);

// Installable app + offline shell (not in demo or development, where a cached build would confuse changes).
if ("serviceWorker" in navigator && import.meta.env.PROD && import.meta.env.VITE_DEMO !== "1") {
  window.addEventListener("load", () => { navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`).catch(() => undefined); });
}
