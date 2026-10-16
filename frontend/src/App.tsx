import { lazy, Suspense, useState } from "react";
import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
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

// Heavier pages load on demand so the first visit stays small and fast.
const StockPage = lazy(() => import("./stock/StockPage").then((m) => ({ default: m.StockPage })));
const Portfolio = lazy(() => import("./pages/Portfolio").then((m) => ({ default: m.Portfolio })));
const Blog = lazy(() => import("./pages/Blog").then((m) => ({ default: m.Blog })));
const BlogPost = lazy(() => import("./pages/Blog").then((m) => ({ default: m.BlogPost })));
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
          <Route path="research" element={<><Research onSearch={() => setSearch(true)} /><SearchPalette open={search} onClose={() => setSearch(false)} /></>} />
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
          <Route path="admin" element={<Admin />} />
          <Route path="admin/login" element={<AdminLogin />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
