import { ImageResponse } from "next/og";

import { markDataUri } from "@/lib/brand";

// The browser tab icon. Next renders this once at build time and serves the PNG.
export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    <div
      style={{
        display: "flex",
        width: "100%",
        height: "100%",
        backgroundImage: `url("${markDataUri(size.width)}")`,
        backgroundSize: `${size.width}px ${size.height}px`,
      }}
    />,
    size,
  );
}
