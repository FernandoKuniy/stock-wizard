import { describe, expect, it } from "vitest";

import { GLOSSARY, slugForTerm } from "@/lib/glossary";

describe("slugForTerm", () => {
  it("kebab-cases a term into an anchor", () => {
    expect(slugForTerm("P/E ratio")).toBe("p-e-ratio");
    expect(slugForTerm("S&P 500")).toBe("s-p-500");
    expect(slugForTerm("dividend")).toBe("dividend");
  });
});

describe("GLOSSARY", () => {
  it("defines the terms the app links to on tap", () => {
    for (const term of [
      "dividend",
      "ex-dividend date",
      "realized gain",
      "unrealized gain",
      "dollar-cost averaging",
      "cost basis",
    ]) {
      expect(GLOSSARY).toHaveProperty(term);
    }
  });

  it("gives every term a unique anchor slug", () => {
    const slugs = Object.keys(GLOSSARY).map(slugForTerm);
    expect(new Set(slugs).size).toBe(slugs.length);
  });
});
