// WCAG 2.x contrast for every colour pair the UI uses, read straight from src/index.css (light values in
// @theme, dark values in :root[data-theme="dark"]). No dependencies. Run: node web/scripts/contrast.mjs
// (--md prints a Markdown table for docs/DESIGN.md). Exits 1 if a required pair fails.
// Tints (bg-pass/12 and friends) are mixed in OKLab, as Tailwind's color-mix(in oklab, ...) does.
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
const block = (re) => Object.fromEntries([...re.exec(css)[1].matchAll(/--color-([\w-]+):\s*(oklch\([^)]*\))/g)].map((m) => [m[1], m[2]]));
const light = block(/@theme static \{([\s\S]*?)\n\}/);
const dark = { ...light, ...block(/:root\[data-theme="dark"\] \{([\s\S]*?)\}/) };

const toLab = (s) => {
  const [L, C, H] = /oklch\(([\d.]+) ([\d.]+) ([\d.]+)\)/.exec(s).slice(1).map(Number);
  return [L, C * Math.cos((H * Math.PI) / 180), C * Math.sin((H * Math.PI) / 180)];
};
const labToRgb = ([L, a, b]) => {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((v) => Math.min(1, Math.max(0, v))); // linear sRGB, clipped to gamut
};
const gamma = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);
export const hex = (lab) => "#" + labToRgb(lab).map((v) => Math.round(gamma(v) * 255).toString(16).padStart(2, "0")).join("");
const lum = (lab) => {
  const [r, g, b] = labToRgb(lab);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
const ratio = (x, y) => {
  const [hi, lo] = [lum(x), lum(y)].sort((p, q) => q - p);
  return (hi + 0.05) / (lo + 0.05);
};
const mix = (fg, bg, p) => fg.map((v, i) => v * p + bg[i] * (1 - p));

// [foreground, background, tint over the background (fraction), minimum]: 4.5 for text, 3 for marks and controls
const PAIRS = [
  ...["ink", "ink-soft", "accent", "pass", "stepup", "block"].flatMap((fg) =>
    ["canvas", "surface", "sunken"].map((bg) => [fg, bg, null, 4.5])),
  ["pass", "surface", ["pass", 0.12], 4.5],
  ["stepup", "surface", ["stepup", 0.12], 4.5],
  ["block", "surface", ["block", 0.12], 4.5],
  ["accent", "surface", ["accent", 0.12], 4.5],
  ["ink", "surface", ["accent", 0.15], 4.5],
  ["ink", "surface", ["block", 0.12], 4.5],
  ["on-accent", "accent", null, 4.5],
  ["on-accent", "pass", null, 4.5],
  ["on-accent", "block", null, 4.5],
  ["on-fill", "pass-fill", null, 4.5],
  ["on-fill", "stepup-fill", null, 4.5],
  ["on-fill", "block-fill", null, 4.5],
  ["accent", "canvas", null, 3],
  ["line-strong", "surface", null, 3],
  ["line-strong", "canvas", null, 3],
  ["advisory", "sunken", null, 3],
  ["pass", "sunken", null, 3],
  ["block", "sunken", null, 3],
];

const rows = [];
for (const [theme, t] of [["dark", dark], ["light", light]]) {
  const get = (k) => toLab(t[k] ?? t[{ advisory: "ink-soft" }[k]]);
  for (const [fg, bg, tint, need] of PAIRS) {
    const back = tint ? mix(get(tint[0]), get(bg), tint[1]) : get(bg);
    const r = ratio(get(fg), back);
    rows.push({ theme, fg, bg: tint ? `${tint[0]}/${tint[1] * 100} on ${bg}` : bg, ratio: r, need, ok: r >= need });
  }
}

if (process.argv.includes("--md")) {
  console.log("| Theme | Foreground | Background | Ratio | Needs |\n|---|---|---|---|---|");
  for (const r of rows) console.log(`| ${r.theme} | \`${r.fg}\` | \`${r.bg}\` | ${r.ratio.toFixed(2)} | ${r.need} |`);
} else if (process.argv.includes("--tokens")) {
  for (const [theme, t] of [["dark", dark], ["light", light]])
    for (const [k, v] of Object.entries(t)) if (v.startsWith("oklch")) console.log(theme, k, v, hex(toLab(v)));
} else {
  for (const r of rows) console.log(`${r.ok ? "ok  " : "FAIL"} ${r.theme.padEnd(5)} ${r.fg.padEnd(11)} on ${r.bg.padEnd(22)} ${r.ratio.toFixed(2).padStart(5)} (needs ${r.need})`);
}
const failed = rows.filter((r) => !r.ok);
if (failed.length) {
  console.error(`${failed.length} pair(s) below WCAG AA`);
  process.exit(1);
}
