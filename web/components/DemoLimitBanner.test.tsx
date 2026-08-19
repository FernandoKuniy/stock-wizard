import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DemoLimitBanner } from "@/components/DemoLimitBanner";

describe("DemoLimitBanner", () => {
  it("says the question is spent and points at a way to get more", () => {
    render(<DemoLimitBanner onUpgrade={vi.fn()} />);
    expect(screen.getByText(/that was your free question/i)).toBeInTheDocument();
    // The link is the whole point of the banner: a demo that can't say who to ask is a
    // dead end, so it must survive any future copy edit.
    expect(screen.getByRole("link", { name: /ask me for a code/i })).toHaveAttribute(
      "href",
      "https://fernando-kuniy.vercel.app/",
    );
  });

  it("says the rest of the app still works", () => {
    render(<DemoLimitBanner onUpgrade={vi.fn()} />);
    expect(screen.getByText(/keep buying, selling/i)).toBeInTheDocument();
  });

  it("will not submit an empty code", async () => {
    const onUpgrade = vi.fn();
    render(<DemoLimitBanner onUpgrade={onUpgrade} />);
    expect(screen.getByRole("button", { name: /unlock/i })).toBeDisabled();
    expect(onUpgrade).not.toHaveBeenCalled();
  });

  it("passes a submitted code up, trimmed", async () => {
    const onUpgrade = vi.fn().mockResolvedValue(null);
    render(<DemoLimitBanner onUpgrade={onUpgrade} />);

    await userEvent.type(screen.getByLabelText(/enter a code/i), "  real-code  ");
    await userEvent.click(screen.getByRole("button", { name: /unlock/i }));

    expect(onUpgrade).toHaveBeenCalledWith("real-code");
  });

  it("shows the reason when the code doesn't work", async () => {
    const onUpgrade = vi.fn().mockResolvedValue("That code didn't unlock it.");
    render(<DemoLimitBanner onUpgrade={onUpgrade} />);

    await userEvent.type(screen.getByLabelText(/enter a code/i), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /unlock/i }));

    expect(await screen.findByText(/didn't unlock it/i)).toBeInTheDocument();
  });
});
