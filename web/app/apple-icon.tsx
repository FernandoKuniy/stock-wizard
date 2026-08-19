import { ImageResponse } from "next/og";

import { markDataUri } from "@/lib/brand";

// The icon iOS uses when someone saves the app to their home screen. Square corners here:
// iOS masks the icon into its own rounded shape, and rounding it twice leaves a dark halo.
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    <div
      style={{
        display: "flex",
        width: "100%",
        height: "100%",
        backgroundImage: `url("${markDataUri(size.width, 0)}")`,
        backgroundSize: `${size.width}px ${size.height}px`,
      }}
    />,
    size,
  );
}
