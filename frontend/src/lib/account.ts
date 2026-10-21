// Account calls. Each returns plain data or throws ApiError (with the server's code in `.body.status`).
import { apiGet, apiSend } from "./api";
import type { User } from "./auth";
import type { Prefs } from "./prefs";

export type SignInResult = { user: User; csrf: string; mfaSetupRequired: boolean };
export const signUp = (b: { email: string; password: string; name?: string; accept_terms: boolean }) => apiSend("POST", "/api/auth/register", b);
export const verifyEmail = (token: string) => apiSend("POST", "/api/auth/verify-email", { token });
export const resendVerification = (email: string) => apiSend("POST", "/api/auth/resend-verification", { email });
export const signIn = (b: { email: string; password: string; code?: string }) => apiSend<SignInResult>("POST", "/api/auth/login", b);
export const forgotPassword = (email: string) => apiSend("POST", "/api/auth/forgot", { email });
export const resetPassword = (token: string, password: string) => apiSend("POST", "/api/auth/reset", { token, password });

export const updateProfile = (name: string) => apiSend("PATCH", "/api/me", { name });
export const changePassword = (current: string, next: string) => apiSend("POST", "/api/me/password", { current, new: next });
export type SessionRow = { id: string; current: boolean; ip: string | null; agent: string; createdAt: string; lastSeenAt: string };
export const listSessions = () => apiGet<{ sessions: SessionRow[] }>("/api/me/sessions");
export const endSession = (id: string) => apiSend("DELETE", `/api/me/sessions/${encodeURIComponent(id)}`);
export const endOtherSessions = () => apiSend("POST", "/api/me/sessions/end-others");
export const mfaSetup = () => apiSend<{ secret: string; uri: string }>("POST", "/api/me/mfa/setup");
export const mfaEnable = (code: string) => apiSend("POST", "/api/me/mfa/enable", { code });
export const mfaDisable = (code: string) => apiSend("POST", "/api/me/mfa/disable", { code });
export const deleteAccount = (password: string) => apiSend("DELETE", "/api/me", { password });
export const requestPlan = (plan: "silver" | "gold", note?: string) => apiSend("POST", "/api/me/plan-request", { plan, note });

export type SavedState = { portfolio?: { holdings?: { id: string; symbol: string; qty: number; price: number; date?: string; note?: string }[] }; watchlist: { lists?: { id: string; name: string; symbols: string[] }[]; meta?: Record<string, { note?: string; target?: number; added: number }> }; screens: { name: string; state: unknown }[]; prefs: Partial<Prefs> };
export const loadState = () => apiGet<SavedState>("/api/me/state");
export const saveWatchlist = (b: unknown) => apiSend("PUT", "/api/me/watchlist", b);
export const savePortfolio = (holdings: unknown) => apiSend("PUT", "/api/me/portfolio", { holdings });
export const saveScreens = (screens: unknown) => apiSend("PUT", "/api/me/screens", { screens });
export const savePrefs = (p: Prefs) => apiSend("PUT", "/api/me/prefs", p);

export type AdminUser = { id: string; email: string; name: string | null; role: string; plan: Plan3; planUntil: string | null; status: string; verified: boolean; mfa: boolean; createdAt: string; lastLoginAt: string | null };
type Plan3 = "basic" | "silver" | "gold";
export type PlanRequest = { id: number; email: string; plan: Plan3; currentPlan: Plan3; note: string | null; createdAt: string; userId: string };
export type AuditRow = { at: string; actor: string | null; action: string; target: string | null; ip: string | null; meta: Record<string, unknown> };
export const adminUsers = (q: string, page: number) => apiGet<{ users: AdminUser[]; total: number; page: number }>(`/api/admin/users?q=${encodeURIComponent(q)}&page=${page}`);
export const adminPatch = (id: string, b: { plan?: Plan3; plan_days?: number; role?: string; status?: string; verify_email?: boolean }) => apiSend("PATCH", `/api/admin/users/${id}`, b);
export const adminRequests = () => apiGet<{ requests: PlanRequest[] }>("/api/admin/plan-requests");
export const adminDecline = (id: number) => apiSend("POST", `/api/admin/plan-requests/${id}/decline`);
export const adminAudit = () => apiGet<{ events: AuditRow[] }>("/api/admin/audit");
export type DataHealth = { coverage?: { byState: Record<string, number>; mismatches: { symbol: string; lines: string[]; at: string }[]; providerEmpty: { symbol: string; name: string | null }[] }; universe: number; loaded: number; scored: number; queued: number; lastLoad: string | null; calendars?: { resultsAt: string | null; resultsThrough: string | null; ipoAt: string | null }; runs24h: Record<string, number>; recentProblems: { symbol: string; status: string; at: string; detail: string }[]; funds?: { etf: { n: number; active: number; last: string | null } | null; mf: { n: number; active: number; with_history: number; last: string | null } | null } };
export const adminHealth = () => apiGet<DataHealth>("/api/admin/data-health");

export const addIpo = (b: Record<string, unknown>) => apiSend("POST", "/api/admin/ipos", b);
export const deleteIpo = (id: number) => apiSend("DELETE", `/api/admin/ipos/${id}`);
export const addFeed = (b: Record<string, unknown>) => apiSend("POST", "/api/admin/feed", b);
export const deleteFeed = (id: number) => apiSend("DELETE", `/api/admin/feed/${id}`);
