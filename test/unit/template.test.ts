// Tests for {{var}} template rendering
import { expect, test } from "vitest";
import { render } from "../../src/lib/template.js";

test("render substitutes every placeholder", () => {
  expect(render("img {{registry}}/apps/{{name}}", { registry: "r:1", name: "hello" })).toBe("img r:1/apps/hello");
});

test("render rejects unknown placeholders", () => {
  expect(() => render("{{missing}}", {})).toThrow(/missing/);
});
