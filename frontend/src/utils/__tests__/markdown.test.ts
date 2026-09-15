import { describe, it, expect } from "vitest";
import { renderMarkdownToSafeHtml } from "../markdown";

describe("renderMarkdownToSafeHtml", () => {
  it("strips <script> tags (XSS)", () => {
    const html = renderMarkdownToSafeHtml("<script>alert('xss')</script>hello");
    expect(html).not.toContain("<script");
    expect(html).not.toContain("alert('xss')");
    expect(html).toContain("hello");
  });

  it("strips inline event handlers", () => {
    const html = renderMarkdownToSafeHtml('<img src="x" onerror="alert(1)">');
    expect(html).not.toContain("onerror");
  });

  it("renders headings and bold markdown", () => {
    const html = renderMarkdownToSafeHtml("# Title\n\n**bold** text");
    expect(html).toContain("<h1");
    expect(html).toContain("<strong>bold</strong>");
  });
});
