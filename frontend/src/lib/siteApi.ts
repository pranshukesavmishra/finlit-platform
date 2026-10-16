// Client for the existing FinLit site backend (Financial-Portfolio/backend/server.py):
// content/CMS, portfolio report, contact, service enquiries, chat, market ticker, admin.
import { apiGet, apiUrl, ApiError } from "./api";

export type ContentItem = {
  id: string; title: string; slug: string; excerpt: string; author: string;
  contentType: "ARTICLE" | "PDF" | "SPREADSHEET" | "IMAGE" | "FILE";
  status: "DRAFT" | "PUBLISHED"; publishedAt?: string | null; updatedAt?: string; createdAt?: string;
  coverImageUrl?: string | null; coverImageKey?: string | null; articleHtml?: string; articleBody?: string;
  fileKey?: string | null; fileUrl?: string | null; originalFileName?: string | null; mimeType?: string | null; fileSize?: number | null;
};
export type PortfolioReport = {
  sourceFileName: string; generatedAt: string;
  profile: { reportPeriod: string; financialYear: string; deployedCapital: string };
  headline: { grossPnl: string; netPnl: string; grossRoi: string; netRoi: string };
  metrics: { key: string; label: string; value: string; tone?: string }[];
  charges: { total: number; totalFormatted: string; breakdown: Record<string, number> };
  tradeLedger: { security: string; symbol: string; quantity: number; buyDate: string; sellDate: string; holdingDays: number; realizedPnl: number }[];
  summary: { tradeCount: number; winningTrades: number; losingTrades: number; zeroPnlTrades: number };
  charts: {
    pnlAttribution: { stock: string; realizedPnl: number }[]; monthlyRealizedPnl: { month: string; realizedPnl: number }[];
    cumulativeRealizedPnl: { date: string; realizedPnl: number }[]; holdingPeriodDistribution: { bucket: string; trades: number }[];
    outcomes: { outcome: string; trades: number }[]; grossPnl: number;
  };
};
export type TickerItem = { name: string; symbol: string; price: number | null; change?: number | null; changePercent?: number | null; changePct?: number | null; category?: string };

async function send<T>(path: string, body: unknown, token?: string): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data: any = {};
  try { data = text ? JSON.parse(text) : {}; } catch { /* non-JSON */ }
  // The site backend stores a lead first and then emails the team; if only the email step fails it says so.
  // The visitor's message is safe, so show success (the team still sees it in the admin inbox).
  if (!res.ok && typeof data?.detail === "string" && /was saved/i.test(data.detail)) return {} as T;
  if (!res.ok) throw new ApiError(res.status, { detail: friendlyError(data, res.status) });
  return data as T;
}

/** FastAPI returns validation errors as a list; turn them into a sentence a visitor can act on. */
function friendlyError(data: any, status: number): string {
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const first = d[0];
    const field = Array.isArray(first.loc) ? String(first.loc[first.loc.length - 1]) : "";
    const msg = String(first.msg || "").replace(/^Value error, /, "");
    return field && !/valid|enter/i.test(msg) ? `${field[0].toUpperCase()}${field.slice(1)}: ${msg}` : msg || "Please check the form and try again.";
  }
  if (status === 429) return "Too many requests. Please wait a little and try again.";
  return "Something went wrong. Please try again.";
}

export const getContent = (type?: string) => apiGet<ContentItem[]>(`/api/content${type ? `?content_type=${encodeURIComponent(type)}` : ""}`);
export const getContentItem = (slug: string) => apiGet<ContentItem>(`/api/content/${encodeURIComponent(slug)}`);
export const getPortfolio = () => apiGet<PortfolioReport>("/api/portfolio/report");
export const getTicker = () => apiGet<{ items: TickerItem[] }>("/api/market-ticker");
export const assetUrl = (key: string) => apiUrl(`/api/content/assets/${encodeURIComponent(key)}`);

export type ContactPayload = { name: string; email: string; phone?: string; investment_size?: string; subject?: string; message?: string };
export const sendContact = (p: ContactPayload) => send<{ id?: string }>("/api/contact", p);
export const sendEnquiry = (p: { name: string; email: string; phone: string; services: string[]; message?: string }) => send<{ id?: string }>("/api/service-enquiry", p);
export const askAssistant = (message: string, history: { role: "user" | "assistant"; content: string }[]) =>
  send<{ response: string }>("/api/chat", { message, history: history.slice(-12) });
export const adminLogin = (email: string, password: string) => send<{ token: string; expiresIn: number }>("/api/content/admin/login", { email, password });
