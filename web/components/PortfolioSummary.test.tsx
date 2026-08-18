import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PortfolioSummary } from "@/components/PortfolioSummary";
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

describe("PortfolioSummary", () => {
  it("shows the total value and that you're up since you started", () => {
    render(
      <PortfolioSummary portfolio={makePortfolio({ total_value: 100500, total_gain_loss: 500 })} />,
    );
    expect(screen.getByText("$100,500.00")).toBeInTheDocument();
    expect(screen.getByText(/since you started/)).toHaveTextContent("up");
  });

  it("shows the dividend line only once something has paid out", () => {
    const { rerender } = render(
      <PortfolioSummary portfolio={makePortfolio({ dividend_income: 0 })} />,
    );
    expect(screen.queryByRole("button", { name: /dividends/i })).not.toBeInTheDocument();

    rerender(<PortfolioSummary portfolio={makePortfolio({ dividend_income: 42 })} />);
    expect(screen.getByRole("button", { name: /dividends/i })).toBeInTheDocument();
    expect(screen.getByText("$42.00")).toBeInTheDocument();
  });

  it("offers to explain what moved your money", () => {
    render(
      <PortfolioSummary portfolio={makePortfolio({ what_moved: "AAPL did the heavy lifting." })} />,
    );
    expect(screen.getByText("AAPL did the heavy lifting.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /explain this to me/i })).toBeInTheDocument();
  });
});
