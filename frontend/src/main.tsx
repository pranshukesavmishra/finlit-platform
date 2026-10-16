import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { UIProvider } from "./lib/ui";
import "./styles/finlit.css";
import "./styles/site.css";
import { installDemo } from "./lib/demo";

installDemo();

const client = new QueryClient({ defaultOptions: { queries: { refetchOnWindowFocus: false } } });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
        <UIProvider>
          <App />
        </UIProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
