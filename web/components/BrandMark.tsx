import {
  BRAND,
  MARK_LINE_PATH,
  MARK_LINE_WIDTH,
  MARK_RADIUS,
  MARK_SPARK_PATH,
  MARK_VIEWBOX,
} from "@/lib/brand";

/**
 * The Stock Wizard mark, rendered inline for the header.
 *
 * Inline SVG rather than an <img> pointing at /icon: it's a handful of bytes in the HTML with
 * no second request, and it stays crisp at any size. The geometry comes from lib/brand, the
 * same constants the favicon, the iOS icon and the social card are built from, so there is one
 * shape to change rather than four.
 *
 * Decorative, so it's hidden from assistive tech: the wordmark beside it already says the name,
 * and a screen reader announcing it twice would be noise.
 */
export function BrandMark({ size = 22 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={MARK_VIEWBOX}
      aria-hidden="true"
      focusable="false"
      className="shrink-0"
    >
      <rect width="32" height="32" rx={MARK_RADIUS} fill={BRAND.tile} />
      <path d={MARK_SPARK_PATH} fill={BRAND.spark} />
      <path
        d={MARK_LINE_PATH}
        fill="none"
        stroke={BRAND.line}
        strokeWidth={MARK_LINE_WIDTH}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
