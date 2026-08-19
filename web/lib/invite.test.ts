import { describe, expect, it } from "vitest";

import { INVITE_CODE_KEY, inviteCodeFrom } from "@/lib/invite";

describe("inviteCodeFrom", () => {
  it("reads the code stashed at signup", () => {
    expect(inviteCodeFrom({ [INVITE_CODE_KEY]: "ripozzy" })).toBe("ripozzy");
  });

  it("trims whitespace someone pasted in with the code", () => {
    expect(inviteCodeFrom({ [INVITE_CODE_KEY]: "  ripozzy \n" })).toBe("ripozzy");
  });

  it("has nothing for a user who signed up before codes travelled in metadata", () => {
    expect(inviteCodeFrom({})).toBeNull();
    expect(inviteCodeFrom({ some_other_key: "x" })).toBeNull();
  });

  it("survives the shapes reality produces", () => {
    // Metadata comes off a Supabase user, so it can be absent or null entirely, and the
    // value is whatever was written there. Returning null just means "ask them for a code".
    expect(inviteCodeFrom(null)).toBeNull();
    expect(inviteCodeFrom(undefined)).toBeNull();
    expect(inviteCodeFrom("not an object")).toBeNull();
    expect(inviteCodeFrom({ [INVITE_CODE_KEY]: 42 })).toBeNull();
    expect(inviteCodeFrom({ [INVITE_CODE_KEY]: null })).toBeNull();
  });

  it("treats a blank code as no code", () => {
    // An empty string would otherwise be sent to the API as a redeem attempt and 403, which
    // reads to the user as "your code was wrong" when they never gave one.
    expect(inviteCodeFrom({ [INVITE_CODE_KEY]: "   " })).toBeNull();
  });
});
