import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TransactionsTable } from "@/components/TransactionsTable";
import type { Transaction } from "@/lib/api";

const txns: Transaction[] = [
  {
    id: 1,
    symbol: "AAPL",
    side: "buy",
    quantity: 10,
    price: 150,
    total: 1500,
    timestamp: "2026-03-15T20:00:00Z",
  },
  {
    id: 2,
    symbol: "MSFT",
    side: "sell",
    quantity: 5,
    price: 300,
    total: 1500,
    timestamp: "2026-03-16T20:00:00Z",
  },
];

describe("TransactionsTable", () => {
  it("shows an empty state with no trades", () => {
    render(<TransactionsTable transactions={[]} />);
    expect(screen.getByText(/no trades yet/i)).toBeInTheDocument();
  });

  it("renders a row per trade with a buy/sell badge and a link to the stock", () => {
    render(<TransactionsTable transactions={txns} />);
    expect(screen.getByText("Buy")).toBeInTheDocument();
    expect(screen.getByText("Sell")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "AAPL" })).toHaveAttribute("href", "/stock/AAPL");
  });
});
