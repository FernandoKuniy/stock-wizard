import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TutorPanel } from "@/components/TutorPanel";
import { askTutorAbout } from "@/lib/tutor-bus";

// The tutor talks to the backend and to Supabase; neither belongs in a jsdom test. Mocking
// them leaves the panel's own behaviour, which is what these cover.
const streamTutor = vi.fn();

vi.mock("@/lib/api", () => ({
  streamTutor: (...args: unknown[]) => streamTutor(...args),
  askTutor: vi.fn(),
  redeemInvite: vi.fn(),
  isDemoLimitReached: () => false,
}));

vi.mock("@/lib/supabase/client", () => ({
  getAccessToken: vi.fn().mockResolvedValue("token"),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn() }),
}));

describe("TutorPanel", () => {
  beforeEach(() => {
    streamTutor.mockReset();
    // Answer with one chunk, so a question completes rather than hanging as "busy".
    streamTutor.mockImplementation(
      async (_messages: unknown, _token: unknown, onDelta: (delta: string) => void) => {
        onDelta("Because your biggest positions are up.");
      },
    );
  });

  afterEach(() => vi.clearAllMocks());

  const open = () => screen.getByRole("button", { name: /ask the tutor/i });
  // The click-away backdrop is a close control too and carries the same label, so scope to
  // the dialog to get the × rather than matching both.
  const closeButton = () =>
    within(screen.getByRole("dialog")).getByRole("button", { name: /close the tutor/i });

  it("asks an explain-this question once, and not again on every reopen", async () => {
    const user = userEvent.setup();
    render(<TutorPanel />);

    // An "explain this" button elsewhere in the app fires this.
    askTutorAbout("Why is my portfolio beating the market?");
    await waitFor(() => expect(streamTutor).toHaveBeenCalledTimes(1));

    // The regression: the tutor unmounts with the panel, so its own "already asked" guard was
    // lost on reopen while the question wasn't, and it re-sent every single time.
    await user.click(closeButton());
    await user.click(open());
    await user.click(closeButton());
    await user.click(open());

    expect(streamTutor).toHaveBeenCalledTimes(1);
  });

  it("asks again when the explain-this button is pressed again", async () => {
    const user = userEvent.setup();
    render(<TutorPanel />);

    askTutorAbout("Why is my portfolio beating the market?");
    await waitFor(() => expect(streamTutor).toHaveBeenCalledTimes(1));
    await user.click(closeButton());

    // A fresh press is a fresh question, so this one does have to send.
    askTutorAbout("Why is my portfolio beating the market?");
    await waitFor(() => expect(streamTutor).toHaveBeenCalledTimes(2));
  });

  it("opens itself when an explain-this question arrives", async () => {
    render(<TutorPanel />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    askTutorAbout("Am I diversified?");
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());
  });

  it("does not ask anything when simply opened by hand", async () => {
    const user = userEvent.setup();
    render(<TutorPanel />);

    await user.click(open());
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(streamTutor).not.toHaveBeenCalled();
  });
});
