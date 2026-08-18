import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ReturnsBreakdown } from "@/components/ReturnsBreakdown";
import type { Portfolio } from "@/lib/api";

function makePortfolio(overrides: Partial<Portfolio> = {}): Portfolio {
  return {
    cash: 50000,
    starting_balance: 100000,
    total_value: 100500,
    total_cost_basis: 50000,
    total_gain_loss: 500,
    total_gain_loss_percent: 0.5,
    cash_weight: 49.75,
    holdings: [],
    unpriced_symbols: [],
    what_moved: null,
    achievements: [],
    is_sample: false,
    dividend_income: 0,
    realized_gain: 200,
    unrealized_gain: 300,
    ...overrides,
  };
}

describe("ReturnsBreakdown", () => {
  it("shows locked-in, on-paper, and an explain button", () => {
    render(
      <ReturnsBreakdown portfolio={makePortfolio({ realized_gain: 200, unrealized_gain: 300 })} />,
    );
    expect(screen.getByRole("button", { name: /locked in/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /on paper/i })).toBeInTheDocument();
    expect(screen.getByText("+$200.00")).toBeInTheDocument();
    expect(screen.getByText("+$300.00")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /explain this to me/i })).toBeInTheDocument();
  });

  it("shows a loss in red-worthy negative form", () => {
    render(<ReturnsBreakdown portfolio={makePortfolio({ realized_gain: -50 })} />);
    expect(screen.getByText("-$50.00")).toBeInTheDocument();
  });
});
