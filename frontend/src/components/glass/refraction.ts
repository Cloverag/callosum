/**
 * The refraction half of Meridian's glass, as SVG filter primitives.
 *
 * ---------------------------------------------------------------------------
 * WHY THIS IS NOT CSS
 * ---------------------------------------------------------------------------
 * `.surface-glass` was `backdrop-filter: blur(20px) saturate(1.4)` — frost, not
 * glass. Frost scatters what is behind it; glass *displaces* it first. The
 * displacement needs `feDisplacementMap`, which means an SVG filter, which means
 * `backdrop-filter: url(#…)`.
 *
 * Three things about that are not obvious and each one cost a rendered-nothing
 * debugging pass:
 *
 *   1. `backdrop-filter: url(var(--x))` never parses. `url()` is a single CSS
 *      token and `var()` is not substituted inside it — the browser looks for a
 *      resource literally named `var(--x)`, finds none, and drops the whole
 *      declaration silently. The filter id has to be written into the property.
 *
 *   2. A shared filter in the default `objectBoundingBox` units has no bounding
 *      box to resolve against when what it is filtering is a *backdrop*. Every
 *      surface needs its own filter in `userSpaceOnUse` at its own pixel size,
 *      rebuilt when it resizes.
 *
 *   3. Displacement and blur cannot be split across two stacked CSS layers. An
 *      element with `backdrop-filter` becomes a Backdrop Root, so a child's own
 *      `backdrop-filter` can no longer see past it and ends up blurring an empty
 *      backdrop. Both have to be primitives in the same chain, in this order:
 *      displace, then blur, then saturate. Blur first and there is no detail
 *      left to bend.
 *
 * The CSS `blur() saturate()` on the utility class stays as the fallback and
 * needs no feature test: where `url()` applied, the element is a Backdrop Root
 * and that declaration is inert; where it did not, the element is not a root and
 * that declaration is the only frost there is. Safari and Firefox land on the
 * old look with no branch written.
 */

/** Which chain a surface gets. Chrome takes `lens`; overlays take `dispersion`. */
export type GlassTier = "lens" | "dispersion";

/**
 * The tuned material, owner's values (2026-09-02).
 *
 * Deliberately near-threshold: the bend is 2px spread across an 80px band, so
 * saturation carries most of the perceived effect and the glass reads as clear
 * rather than frosted. These live here rather than in `globals.css` because SVG
 * filter primitives take attributes, not custom properties — a token would have
 * to be read back out with `getComputedStyle` on every resize to reach them.
 */
export const GLASS = {
  /** `feGaussianBlur` stdDeviation, applied AFTER displacement. */
  blur: 1,
  /** `feColorMatrix type="saturate"`. Glass concentrates colour. */
  saturate: 1.8,
  /** Peak lateral shove in pixels, at the rim. */
  bend: 2,
  /** How far in from the border the bend ramps, in pixels. */
  band: 80,
  /** How much fractal noise is mixed into the lens map. */
  noise: 0.14,
  /** `feTurbulence` baseFrequency. */
  frequency: 0.007,
  /** `feTurbulence` numOctaves. */
  octaves: 1,
  /** Per-channel spread for the dispersion tier, as a fraction of `bend`. */
  dispersion: 0.3,
} as const;

const SVG_NS = "http://www.w3.org/2000/svg";
const XLINK_NS = "http://www.w3.org/1999/xlink";

/**
 * The displacement map: neutral through the middle, ramping only at the rim.
 *
 * `feDisplacementMap` reads a channel value of 0.5 as "do not move this pixel",
 * so a mid-grey interior passes the backdrop straight through and only the band
 * bends it. R carries the horizontal shove and G the vertical, which is why this
 * is two gradients screened together rather than one: a single gradient cannot
 * carry an independent horizontal R and vertical G.
 *
 * At the rim, R is 0 on the left and 255 on the right. Both sample *outward*,
 * so content is pulled inward from either side — the squeeze you see at the edge
 * of a real pane, rather than a uniform smear.
 */
export function lensMapURI(width: number, height: number, band: number): string {
  const ex = Math.min(0.49, band / Math.max(width, 1));
  const ey = Math.min(0.49, band / Math.max(height, 1));
  const stops = (axis: "x" | "y", channel: "R" | "G") => {
    const lit = channel === "R" ? "rgb(255,0,0)" : "rgb(0,255,0)";
    const mid = channel === "R" ? "rgb(128,0,0)" : "rgb(0,128,0)";
    const inset = axis === "x" ? ex : ey;
    return (
      `<stop offset="0" stop-color="rgb(0,0,0)"/>` +
      `<stop offset="${inset.toFixed(4)}" stop-color="${mid}"/>` +
      `<stop offset="${(1 - inset).toFixed(4)}" stop-color="${mid}"/>` +
      `<stop offset="1" stop-color="${lit}"/>`
    );
  };

  const svg =
    `<svg xmlns="${SVG_NS}" width="${width}" height="${height}">` +
    `<defs>` +
    `<linearGradient id="x" x1="0" y1="0" x2="1" y2="0">${stops("x", "R")}</linearGradient>` +
    `<linearGradient id="y" x1="0" y1="0" x2="0" y2="1">${stops("y", "G")}</linearGradient>` +
    `</defs>` +
    `<rect width="${width}" height="${height}" fill="url(%23x)"/>` +
    `<rect width="${width}" height="${height}" fill="url(%23y)" style="mix-blend-mode:screen"/>` +
    `</svg>`;

  // `%23` for the fragment references is written in above rather than encoded out
  // here: encodeURIComponent would turn it into `%2523` and the gradient would
  // silently resolve to nothing, leaving a black map that displaces everything
  // by the full scale in one direction.
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg).replace(/%25/g, "%")}`;
}

function node(name: string, attrs: Record<string, string | number>): SVGElement {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, String(value));
  return element;
}

/**
 * Build one surface's filter, sized in user space to its own box.
 *
 * `dispersion` runs the displacement three times at slightly different strengths
 * and keeps one colour channel from each, so the rim carries a fringe. It is
 * three extra passes over the backdrop and is reserved for the few floating
 * overlays rather than spent on chrome that is on screen at all times.
 */
export function buildFilter(id: string, tier: GlassTier, width: number, height: number): SVGElement {
  const filter = node("filter", {
    id,
    filterUnits: "userSpaceOnUse",
    x: 0,
    y: 0,
    width,
    height,
    "color-interpolation-filters": "sRGB",
  });

  const map = node("feImage", {
    x: 0,
    y: 0,
    width,
    height,
    preserveAspectRatio: "none",
    result: "lens",
  });
  const uri = lensMapURI(width, height, GLASS.band);
  map.setAttribute("href", uri);
  // Chromium honours `href`; the xlink form is set too because some engines that
  // parse the filter still resolve only the legacy attribute, and a feImage that
  // resolves to nothing yields a transparent map — which displaces by half the
  // scale everywhere rather than failing visibly.
  map.setAttributeNS(XLINK_NS, "href", uri);
  filter.appendChild(map);

  filter.appendChild(
    node("feTurbulence", {
      type: "fractalNoise",
      baseFrequency: GLASS.frequency,
      numOctaves: GLASS.octaves,
      seed: 17,
      result: "noise",
    }),
  );
  filter.appendChild(node("feGaussianBlur", { in: "noise", stdDeviation: 1.1, result: "softNoise" }));

  // Noise is mixed INTO the lens map rather than swapping for it: cast-glass
  // irregularity on top of the edge behaviour, not one instead of the other.
  filter.appendChild(
    node("feComposite", {
      in: "softNoise",
      in2: "lens",
      operator: "arithmetic",
      k1: 0,
      k2: GLASS.noise,
      k3: (1 - GLASS.noise * 0.4).toFixed(3),
      k4: 0,
      result: "map",
    }),
  );

  if (tier === "lens") {
    filter.appendChild(
      node("feDisplacementMap", {
        in: "SourceGraphic",
        in2: "map",
        scale: GLASS.bend,
        xChannelSelector: "R",
        yChannelSelector: "G",
        result: "bent",
      }),
    );
  } else {
    const spread = GLASS.dispersion;
    const passes: Array<[string, number, string]> = [
      ["pr", GLASS.bend * (1 + spread), "1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"],
      ["pg", GLASS.bend, "0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0"],
      ["pb", GLASS.bend * (1 - spread), "0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"],
    ];
    for (const [name, scale, matrix] of passes) {
      filter.appendChild(
        node("feDisplacementMap", {
          in: "SourceGraphic",
          in2: "map",
          scale,
          xChannelSelector: "R",
          yChannelSelector: "G",
          result: name,
        }),
      );
      filter.appendChild(node("feColorMatrix", { in: name, type: "matrix", values: matrix, result: `m${name}` }));
    }
    filter.appendChild(
      node("feComposite", { in: "mpr", in2: "mpg", operator: "arithmetic", k1: 0, k2: 1, k3: 1, k4: 0, result: "mrg" }),
    );
    filter.appendChild(
      node("feComposite", { in: "mrg", in2: "mpb", operator: "arithmetic", k1: 0, k2: 1, k3: 1, k4: 0, result: "bent" }),
    );
  }

  filter.appendChild(node("feGaussianBlur", { in: "bent", stdDeviation: GLASS.blur, result: "soft" }));
  filter.appendChild(node("feColorMatrix", { in: "soft", type: "saturate", values: GLASS.saturate }));
  return filter;
}
