import { lazy, Suspense, useState } from "react";
import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { AppShell } from "./components/AppShell";
import { SearchPalette } from "./components/SearchPalette";
import { Home } from "./pages/Home";
import { Research } from "./pages/Research";
import { PlansPage } from "./pages/Plans";
import { Services } from "./pages/Services";
import { About } from "./pages/About";
import { Why } from "./pages/Why";
import { Contact } from "./pages/Contact";
import { Legal, NotFound } from "./pages/Legal";
import { Login } from "./pages/Login";
import { ForgotPassword, ResetPassword, VerifyEmail } from "./pages/AccountFlows";

// Heavier pages load on demand so the first visit stays small and fast.
const StockPage = lazy(() => import("./stock/StockPage").then((m) => ({ default: m.StockPage })));
const Portfolio = lazy(() => import("./pages/Portfolio").then((m) => ({ default: m.Portfolio })));
const Blog = lazy(() => import("./pages/Blog").then((m) => ({ default: m.Blog })));
const BlogPost = lazy(() => import("./pages/Blog").then((m) => ({ default: m.BlogPost })));
const Screener = lazy(() => import("./pages/Screener").then((m) => ({ default: m.Screener })));
const Compare = lazy(() => import("./pages/Compare").then((m) => ({ default: m.Compare })));
const GlossaryPage = lazy(() => import("./pages/Glossary").then((m) => ({ default: m.GlossaryPage })));
const WatchlistPage = lazy(() => import("./pages/Watchlist").then((m) => ({ default: m.WatchlistPage })));
const Account = lazy(() => import("./pages/Account").then((m) => ({ default: m.Account })));
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const Console = lazy(() => import("./pages/Console").then((m) => ({ default: m.Console })));
const IpoPage = lazy(() => import("./pages/Ipo").then((m) => ({ default: m.IpoPage })));
const ResultsPage = lazy(() => import("./pages/Results").then((m) => ({ default: m.ResultsPage })));
const NewsPage = lazy(() => import("./pages/News").then((m) => ({ default: m.NewsPage })));
const DocumentsPage = lazy(() => import("./pages/Documents").then((m) => ({ default: m.DocumentsPage })));
const AlertsPage = lazy(() => import("./pages/Alerts").then((m) => ({ default: m.AlertsPage })));
const HoldingsPage = lazy(() => import("./pages/Holdings").then((m) => ({ default: m.HoldingsPage })));
const Admin = lazy(() => import("./pages/Admin").then((m) => ({ default: m.Admin })));
const AdminLogin = lazy(() => import("./pages/Admin").then((m) => ({ default: m.AdminLogin })));

const Fallback = () => <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 200, margin: "0 auto" }} /></div>;

export default function App() {
  const [search, setSearch] = useState(false);
  return (
    <Suspense fallback={<Fallback />}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route element={<AppShell />}>
            <Route path="research" element={<><Research onSearch={() => setSearch(true)} /><SearchPalette open={search} onClose={() => setSearch(false)} /></>} />
            <Route path="dashboard" element={<Dashboard />} />
            <Route path="screener" element={<Screener />} />
            <Route path="compare" element={<Compare />} />
            <Route path="watchlist" element={<WatchlistPage />} />
            <Route path="holdings" element={<HoldingsPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="ipo" element={<IpoPage />} />
            <Route path="results" element={<ResultsPage />} />
            <Route path="news" element={<NewsPage />} />
            <Route path="documents" element={<DocumentsPage />} />
            <Route path="glossary" element={<GlossaryPage />} />
            <Route path="account" element={<Account />} />
            <Route path="account/:tab" element={<Account />} />
            <Route path="console" element={<Console />} />
          </Route>
          <Route path="stocks/:symbol" element={<StockPage />} />
          <Route path="plans" element={<PlansPage />} />
          <Route path="services" element={<Services />} />
          <Route path="about" element={<About />} />
          <Route path="why-we-exist" element={<Why />} />
          <Route path="contact" element={<Contact />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="blog" element={<Blog />} />
          <Route path="blog/:slug" element={<BlogPost />} />
          <Route path="legal/:doc" element={<Legal />} />
          <Route path="login" element={<Login />} />
          <Route path="verify-email" element={<VerifyEmail />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="reset-password" element={<ResetPassword />} />
          <Route path="admin" element={<Admin />} />
          <Route path="admin/login" element={<AdminLogin />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
