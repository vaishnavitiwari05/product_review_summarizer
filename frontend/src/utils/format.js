export const titleCase = (s = "") => s.charAt(0).toUpperCase() + s.slice(1);
export const pct = (n, d = 0) => (n == null ? "–" : `${Number(n).toFixed(d)}%`);
export const num = (n) => (n == null ? "–" : Number(n).toLocaleString("en-US"));

export function dateRange(min, max) {
  if (!min && !max) return "Not available";
  const f = (d) =>
    new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", year: "numeric" });
  return min === max || !max ? f(min) : `${f(min)} – ${f(max)}`;
}

export const SENTIMENT_TONE = {
  Positive: "good",
  "Mostly Positive": "good",
  Mixed: "warn",
  "Mostly Negative": "bad",
  Negative: "bad",
};

/** Donut segments as SVG stroke-dasharray values on a circle of radius r. */
export function donutSegments(values, r = 42) {
  const total = values.reduce((a, b) => a + b, 0) || 1;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return values.map((v) => {
    const len = (v / total) * c;
    const seg = { dash: `${len} ${c - len}`, offset: -offset, length: len };
    offset += len;
    return seg;
  });
}

/** Widths (in %) for a stacked positive/neutral/negative bar, relative to `max` mentions. */
export function stackWidths(a, max) {
  const scale = max ? 100 / max : 0;
  return {
    positive: a.positive * scale,
    neutral: a.neutral * scale,
    negative: a.negative * scale,
  };
}
