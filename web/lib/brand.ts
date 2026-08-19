/**
 * The Stock Wizard mark: a rising portfolio line with a spark above it, on a dark tile.
 *
 * It lives here as an SVG string rather than a checked-in image so the browser tab icon, the
 * iOS home-screen icon, and the social preview card all draw the same shape from one source.
 * `next/og` rasterises them to PNG at build time, and it reads SVG through a data URI, which
 * is why this is a string and not JSX.
 *
 * The line is indigo on purpose: it's the same color the performance chart uses for "your
 * money" (see PerformanceChart), so the icon and the app's main graph match.
 */

export const BRAND = {
  ink: "#0a0a0a", // page background in dark mode
  tile: "#18181b", // the mark's rounded square (zinc-900)
  line: "#818cf8", // the portfolio line (indigo-400)
  spark: "#c7d2fe", // the spark (indigo-200), lighter so it survives a 16px browser tab
  text: "#fafafa",
  muted: "#a1a1aa", // zinc-400
} as const;

/**
 * The mark at any size. `radius` rounds the tile's corners; pass 0 for iOS, which masks the
 * icon into its own shape and looks wrong if we round it first.
 */
export function markSvg(size: number, radius = 7): string {
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32">`,
    `<rect width="32" height="32" rx="${radius}" fill="${BRAND.tile}"/>`,
    // A four-point spark. The curves pull back to the center, which is what makes the arms
    // taper instead of reading as a plus sign.
    `<path d="M8.5 3.5C8.5 8.5 8.5 8.5 13.5 8.5C8.5 8.5 8.5 8.5 8.5 13.5C8.5 8.5 8.5 8.5 3.5 8.5C8.5 8.5 8.5 8.5 8.5 3.5Z" fill="${BRAND.spark}"/>`,
    `<path d="M6 24L13 18L18 21L26 11" fill="none" stroke="${BRAND.line}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`,
    `</svg>`,
  ].join("");
}

/** The same mark as a data URI, the form `next/og` can draw. */
export function markDataUri(size: number, radius = 7): string {
  return `data:image/svg+xml;base64,${Buffer.from(markSvg(size, radius)).toString("base64")}`;
}
