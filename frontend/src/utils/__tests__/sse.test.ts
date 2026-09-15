import { describe, it, expect } from "vitest";
import { parseSseBlock } from "../sse";

describe("parseSseBlock", () => {
  it("extracts a JSON data payload", () => {
    expect(parseSseBlock('data: {"type":"token","data":"hi"}')).toBe(
      '{"type":"token","data":"hi"}'
    );
  });

  it("returns null for empty blocks", () => {
    expect(parseSseBlock("")).toBeNull();
    expect(parseSseBlock("\n")).toBeNull();
  });

  it("strips the data: prefix from plain text", () => {
    expect(parseSseBlock("data: hello")).toBe("hello");
  });
});
