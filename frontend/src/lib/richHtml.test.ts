import { describe, expect, it } from "vitest";
import { htmlIsEmpty, linkOk, normaliseHtml, textToHtml } from "./richHtml";

describe("normaliseHtml", () => {
  it("maps browser tags to the stored set and drops styling and unknown tags", () => {
    expect(normaliseHtml('<div style="x"><b>Hi</b> <i>there</i> <span class="y">you</span></div>')).toBe("<p><strong>Hi</strong> <em>there</em> you</p>");
  });
  it("removes scripts, handlers and comments; keeps only href/title on links", () => {
    const out = normaliseHtml('<!-- c --><p onclick="x()">a</p><script>alert(1)</script><a href="https://e.com" onclick="y()" class="z">l</a>');
    expect(out).toBe('<p>a</p><a href="https://e.com">l</a>');
  });
  it("drops empty paragraphs", () => expect(normaliseHtml("<p><br></p><p>x</p>")).toBe("<p>x</p>"));
});
describe("helpers", () => {
  it("escapes pasted text", () => expect(textToHtml("a <b>x</b>\nb\n\nc & d")).toBe("<p>a &lt;b&gt;x&lt;/b&gt;<br>b</p><p>c &amp; d</p>"));
  it("detects empty html", () => { expect(htmlIsEmpty("<p><br></p>")).toBe(true); expect(htmlIsEmpty('<img src="x">')).toBe(false); });
  it("allows only https links", () => { expect(linkOk("https://a.com")).toBe(true); expect(linkOk("http://a.com")).toBe(false); expect(linkOk("javascript:alert(1)")).toBe(false); });
});
