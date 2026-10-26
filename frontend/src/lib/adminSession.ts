// The admin (CMS) bearer token: same model as the Admin page (sessionStorage, 8 h, signature checked by the server).
// It is only read here to decide what to show; the server checks it again on every request.
export const ADMIN_KEY = "cms_admin_token";
export const adminToken = (): string | null => { try { return sessionStorage.getItem(ADMIN_KEY); } catch { return null; } };
export function hasAdminSession(): boolean {
  const t = adminToken(); if (!t) return false;
  try { const p = JSON.parse(atob(t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); return p.role === "admin" && p.exp * 1000 > Date.now(); } catch { return false; }
}
