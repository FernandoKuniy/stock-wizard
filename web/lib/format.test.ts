import { describe, expect, it } from "vitest";

import {
  formatCompactMoney,
  formatMoney,
  formatPercent,
  formatShares,
  formatShortDate,
  formatSignedMoney,
} from "@/lib/format";

describe("formatMoney", () => {
  it("formats dollars with cents and a symbol", () => {
    expect(formatMoney(1234.5)).toBe("$1,234.50");
    expect(formatMoney(0)).toBe("$0.00");
  });
});

describe("formatSignedMoney", () => {
  it("prefixes a sign, keeps the magnitude, and never trails a space", () => {
    expect(formatSignedMoney(240)).toBe("+$240.00");
    expect(formatSignedMoney(-240)).toBe("-$240.00");
    expect(formatSignedMoney(0)).toBe("$0.00");
  });
});

describe("formatPercent", () => {
  it("prefixes + for a gain, - falls out of the number, two decimals", () => {
    expect(formatPercent(2.4)).toBe("+2.40%");
    expect(formatPercent(-2.4)).toBe("-2.40%");
    expect(formatPercent(0)).toBe("0.00%");
  });
});

describe("formatShares", () => {
  it("shows up to six decimals with no trailing padding", () => {
    expect(formatShares(1.5)).toBe("1.5");
    expect(formatShares(10)).toBe("10");
  });
});

describe("formatCompactMoney", () => {
  it("abbreviates a huge amount", () => {
    expect(formatCompactMoney(2_900_000_000_000)).toBe("$2.9T");
  });
});

describe("formatShortDate", () => {
  it("renders a bare ISO date as a local month and day", () => {
    expect(formatShortDate("2026-03-15")).toBe("Mar 15");
  });
  it("returns empty for a malformed date", () => {
    expect(formatShortDate("nope")).toBe("");
  });
});
