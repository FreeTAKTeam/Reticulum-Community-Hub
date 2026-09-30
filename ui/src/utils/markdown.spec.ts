import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("untrusted formatted output", () => {
  it("escapes active HTML and rejects script links", () => {
    const rendered = renderMarkdown('<img src=x onerror="alert(1)"> [unsafe](javascript:alert(1))');
    expect(rendered).not.toContain("<img");
    expect(rendered).not.toContain('href="javascript:');
    expect(rendered).toContain("&lt;img");
  });

  it("bounds long repeated mailto input and keeps normal Markdown formatting", () => {
    const rendered = renderMarkdown("mailto:".repeat(20000) + "AFTER_LIMIT_SENTINEL");
    expect(rendered).toContain("Output shortened.");
    expect(rendered).not.toContain("AFTER_LIMIT_SENTINEL");
    expect(renderMarkdown("**normal message**")).toContain("<strong>normal message</strong>");
  });
});
