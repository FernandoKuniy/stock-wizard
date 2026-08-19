import { ImageResponse } from "next/og";

import { BRAND, markDataUri } from "@/lib/brand";

// The card that shows up when the link gets pasted into Slack, LinkedIn, iMessage, or a
// tweet. Next reuses this file for the Twitter card too, so there's only one image to keep.
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Stock Wizard: learn investing with fake money and real market prices";

export default function OpengraphImage() {
  return new ImageResponse(
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        width: "100%",
        height: "100%",
        background: BRAND.ink,
        padding: 80,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
        <div
          style={{
            display: "flex",
            width: 104,
            height: 104,
            backgroundImage: `url("${markDataUri(104)}")`,
            backgroundSize: "104px 104px",
          }}
        />
        <div style={{ fontSize: 60, color: BRAND.text, letterSpacing: -1 }}>Stock Wizard</div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div style={{ fontSize: 46, color: BRAND.text, lineHeight: 1.25 }}>
          Learn investing with fake money and real market prices.
        </div>
        <div style={{ fontSize: 30, color: BRAND.muted, lineHeight: 1.4 }}>
          An AI tutor reads your own portfolio and explains it in plain English.
        </div>
      </div>

      <div style={{ fontSize: 24, color: BRAND.muted }}>
        A simulation for learning, not financial advice.
      </div>
    </div>,
    size,
  );
}
