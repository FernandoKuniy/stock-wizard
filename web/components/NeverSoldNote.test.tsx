import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NeverSoldNote } from "@/components/NeverSoldNote";

describe("NeverSoldNote", () => {
  it("says selling has worked out when the difference is positive", () => {
    render(<NeverSoldNote never_sold={{ value: 100000, difference: 250 }} actual={100250} />);
    expect(screen.getByText(/selling has worked out so far/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /explain this to me/i })).toBeInTheDocument();
  });

  it("notes when holding would have left you with more", () => {
    render(<NeverSoldNote never_sold={{ value: 100500, difference: -500 }} actual={100000} />);
    expect(screen.getByText(/more than you/i)).toBeInTheDocument();
  });
});
