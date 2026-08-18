import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Checkup } from "@/components/Checkup";
import type { CheckupFinding } from "@/lib/api";

const findings: CheckupFinding[] = [
  {
    key: "concentration",
    title: "A lot riding on one company",
    status: "notable",
    detail: "AAPL is 60% of your money.",
    lesson: "Spreading out lowers the risk of one bad pick.",
  },
  {
    key: "cash",
    title: "Plenty kept in cash",
    status: "ok",
    detail: "You've got 40% in cash.",
    lesson: "Cash is dry powder for later.",
  },
];

describe("Checkup", () => {
  it("renders nothing when there are no findings", () => {
    const { container } = render(<Checkup findings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists each finding, counts the notable ones, and offers an explain button per row", () => {
    render(<Checkup findings={findings} />);
    expect(screen.getByText("AAPL is 60% of your money.")).toBeInTheDocument();
    expect(screen.getByText("1 worth a look")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /ask the tutor about mine/i })).toHaveLength(2);
  });
});
