import { afterEach, describe, expect, it, vi } from "vitest";
import { adminUpload, adminFetch, buildPayload, canEmbedPdf, coverUrlProblem, draftFrom, draftProblems, emptyDraft, filterItems, fileProblem, parseTags } from "./cms";

const items = [
  { title: "Understanding SIPs", excerpt: "monthly investing", author: "A", status: "PUBLISHED" as const, contentType: "ARTICLE" as const, category: "Basics", tags: ["sip", "mutual funds"] },
  { title: "Q2 results deck", excerpt: "", author: "B", status: "DRAFT" as const, contentType: "PDF" as const, category: "", tags: [] },
  { title: "Sector data", excerpt: "", author: "B", status: "DRAFT" as const, contentType: "SPREADSHEET" as const },
];
afterEach(() => vi.unstubAllGlobals());

describe("filterItems", () => {
  it("filters by status, kind and text (title, tags, category)", () => {
    const all = { q: "", status: "ALL", kind: "ALL" } as const;
    expect(filterItems(items, all)).toHaveLength(3);
    expect(filterItems(items, { ...all, status: "DRAFT" })).toHaveLength(2);
    expect(filterItems(items, { ...all, kind: "PDF" })).toHaveLength(1);
    expect(filterItems(items, { ...all, q: " MUTUAL " })[0].title).toBe("Understanding SIPs");
    expect(filterItems(items, { ...all, q: "basics" })).toHaveLength(1);
    expect(filterItems(items, { q: "sector", status: "PUBLISHED", kind: "ALL" })).toHaveLength(0);
  });
});
describe("rules", () => {
  it("accepts only https cover links", () => {
    expect(coverUrlProblem("")).toBeNull();
    expect(coverUrlProblem("https://example.com/a.png")).toBeNull();
    expect(coverUrlProblem("http://example.com/a.png")).not.toBeNull();
    expect(coverUrlProblem("javascript:alert(1)")).not.toBeNull();
    expect(coverUrlProblem("not a url")).not.toBeNull();
  });
  it("checks file type and size per kind", () => {
    expect(fileProblem({ name: "r.PDF", size: 100 }, "PDF")).toBeNull();
    expect(fileProblem({ name: "r.pdf", size: 100 }, "IMAGE")).not.toBeNull();
    expect(fileProblem({ name: "d.xlsx", size: 100 }, "SPREADSHEET")).toBeNull();
    expect(fileProblem({ name: "a.png", size: 16 * 1024 * 1024 }, "COVER")).toMatch(/larger/);
    expect(fileProblem({ name: "a.png", size: 0 }, "COVER")).toMatch(/empty/);
  });
  it("cleans tags", () => {
    expect(parseTags(" Tax, tax ,SIP  plans,,")).toEqual(["Tax", "SIP plans"]);
    expect(parseTags(Array.from({ length: 20 }, (_, i) => "t" + i).join(","))).toHaveLength(12);
  });
  it("embeds a PDF only from the page's own origin", () => {
    expect(canEmbedPdf("/api/content/assets/x", "https://finlit.in")).toBe(true);
    expect(canEmbedPdf("https://api.finlit.in/api/content/assets/x", "https://finlit.in")).toBe(false);
    expect(canEmbedPdf("blob:https://finlit.in/abc", "https://finlit.in")).toBe(true);
  });
});
describe("draft", () => {
  it("lists what blocks a save", () => {
    expect(draftProblems(emptyDraft())).toHaveLength(2);
    expect(draftProblems({ ...emptyDraft(), title: "Hello", html: "<p>x</p>" })).toEqual([]);
    expect(draftProblems({ ...emptyDraft(), title: "Hello", kind: "PDF" })).toEqual(["Upload the file for this post."]);
    expect(draftProblems({ ...emptyDraft(), title: "Hello", html: "<p>x</p>", coverUrl: "http://x.com/a.png" })).toHaveLength(1);
  });
  it("round-trips an item into a payload, keeping tags and the cover key", () => {
    const d = draftFrom({ id: "1", title: "T title", slug: "t-title", excerpt: "e", author: "A", contentType: "IMAGE", status: "PUBLISHED", fileKey: "f", coverImageKey: "c", tags: ["a", "b"], category: "X" } as any);
    const p = buildPayload(d, "t-title");
    expect(p).toMatchObject({ contentType: "IMAGE", fileKey: "f", coverImageKey: "c", coverImageUrl: undefined, tags: ["a", "b"], category: "X", status: "PUBLISHED", slug: "t-title", articleBody: "" });
  });
});
describe("requests", () => {
  it("uploads as multipart without forcing a JSON content type", async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ key: "k", originalFileName: "a.pdf", mimeType: "application/pdf", fileSize: 3, fileUrl: "/x" }), { status: 200 }));
    vi.stubGlobal("fetch", f);
    const r = await adminUpload(new File(["abc"], "a.pdf", { type: "application/pdf" }));
    expect(r.key).toBe("k");
    const init = f.mock.calls[0][1]; expect(init.body).toBeInstanceOf(FormData); expect(init.headers["Content-Type"]).toBeUndefined();
  });
  it("turns a server error into a message and a 401 into a session-expired error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ detail: "File exceeds the 15 MB limit." }), { status: 413 })).mockResolvedValueOnce(new Response("{}", { status: 401 })));
    await expect(adminFetch("/api/x")).rejects.toThrow(/15 MB/);
    await expect(adminFetch("/api/x")).rejects.toThrow(/expired/);
  });
});
