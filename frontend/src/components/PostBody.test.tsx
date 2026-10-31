import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PostBody } from "./PostBody";

const base = { title: "Report", originalFileName: "r.pdf", fileSize: 2048, articleHtml: "" };
describe("PostBody", () => {
  it("embeds a same-origin PDF", () => {
    const h = renderToStaticMarkup(<PostBody c={{ ...base, contentType: "PDF" }} file="https://finlit.in/api/content/assets/k" origin="https://finlit.in" />);
    expect(h).toContain("<iframe"); expect(h).toContain("Download r.pdf");
  });
  it("falls back to a link for a cross-origin PDF (the service forbids framing it)", () => {
    const h = renderToStaticMarkup(<PostBody c={{ ...base, contentType: "PDF" }} file="https://api.finlit.in/api/content/assets/k" origin="https://finlit.in" />);
    expect(h).not.toContain("<iframe"); expect(h).toContain("Open the PDF"); expect(h).toContain('rel="noopener noreferrer"');
  });
  it("shows an image with alt text, and a spreadsheet as a download", () => {
    expect(renderToStaticMarkup(<PostBody c={{ ...base, contentType: "IMAGE" }} file="/a.png" origin="https://x" />)).toContain('alt="Report"');
    const s = renderToStaticMarkup(<PostBody c={{ ...base, contentType: "SPREADSHEET", originalFileName: "d.xlsx" }} file="/d" origin="https://x" />);
    expect(s).toContain("Spreadsheet"); expect(s).toContain("Download d.xlsx");
  });
  it("says so when the file is missing", () => expect(renderToStaticMarkup(<PostBody c={{ ...base, contentType: "PDF" }} file={null} origin="https://x" />)).toContain("not available"));
});
