"use client";

import { useEffect } from "react";
import { buildFilter, type GlassTier } from "./refraction";

/**
 * Installs real refraction on every surface already wearing a glass utility class.
 *
 * ---------------------------------------------------------------------------
 * WHY IT ATTACHES BY CLASS INSTEAD OF BEING A COMPONENT YOU WRAP THINGS IN
 * ---------------------------------------------------------------------------
 * `.surface-glass` and `.surface-glass-chrome` are already the API. Four call
 * sites use them — `Header`, `AssistantRail` (twice), `ui/dialog` and the
 * `glass` variant of `ui/card` — and they are spread across files this layer
 * does not own. Turning them into a `<GlassSurface>` wrapper would be a rewrite
 * of four components to change a material.
 *
 * So the enhancement is orthogonal: mount this once, and any element that
 * carries the class gets a filter. Elements that appear later — a dialog is
 * mounted on open, not on load — are picked up by the MutationObserver.
 *
 * ---------------------------------------------------------------------------
 * WHAT MAKES IT SAFE TO REMOVE
 * ---------------------------------------------------------------------------
 * Nothing depends on it. Delete the mount and every surface falls back to the
 * `blur() saturate()` in its utility class, which is what shipped before. That
 * is also exactly what a browser without `url()` support in `backdrop-filter`
 * sees, and what a reader who has asked for reduced transparency sees.
 */

/** Chrome is on screen permanently, so it takes the cheaper single-pass chain. */
const TIERS: ReadonlyArray<readonly [string, GlassTier]> = [
  [".surface-glass-chrome", "lens"],
  [".surface-glass", "dispersion"],
];

const SELECTOR = TIERS.map(([selector]) => selector).join(", ");
const DEFS_ID = "meridian-glass-defs";
const MARK = "data-glass-id";

export function GlassRefraction() {
  useEffect(() => {
    // A reader who has asked for less transparency has asked for less of exactly
    // this. Bail before creating anything: the CSS fallback is the honest answer.
    if (window.matchMedia("(prefers-reduced-transparency: reduce)").matches) return;

    // Chromium is the only engine that accepts url() inside backdrop-filter.
    // Elsewhere this would build filters nothing would ever reference.
    if (!CSS.supports("backdrop-filter", "url(#x)") && !CSS.supports("-webkit-backdrop-filter", "url(#x)")) {
      return;
    }

    const host = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    host.setAttribute("id", DEFS_ID);
    host.setAttribute("aria-hidden", "true");
    host.setAttribute("width", "0");
    host.setAttribute("height", "0");
    host.style.position = "absolute";
    host.style.pointerEvents = "none";
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    host.appendChild(defs);
    document.body.appendChild(host);

    let counter = 0;
    const sized = new WeakMap<Element, string>();

    const paint = (element: HTMLElement, tier: GlassTier) => {
      const box = element.getBoundingClientRect();
      const width = Math.round(box.width);
      const height = Math.round(box.height);
      if (width < 1 || height < 1) return;

      // Rebuilding a filter is a repaint of the whole backdrop. A resize that did
      // not change the rounded pixel size is not a reason to pay for one.
      const key = `${width}x${height}`;
      if (sized.get(element) === key) return;
      sized.set(element, key);

      let id = element.getAttribute(MARK);
      if (!id) {
        id = `glass-${counter++}`;
        element.setAttribute(MARK, id);
      }
      defs.querySelector(`#${id}`)?.remove();
      defs.appendChild(buildFilter(id, tier, width, height));

      // Reassigning the property is what invalidates Chromium's cached backdrop.
      // Mutating filter primitives in place does not reliably repaint.
      element.style.backdropFilter = "none";
      void element.offsetWidth;
      element.style.backdropFilter = `url(#${id})`;
    };

    const resize = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const element = entry.target as HTMLElement;
        const tier = TIERS.find(([selector]) => element.matches(selector))?.[1];
        if (tier) paint(element, tier);
      }
    });

    const scan = () => {
      for (const [selector, tier] of TIERS) {
        for (const element of document.querySelectorAll<HTMLElement>(selector)) {
          // `.surface-glass-chrome` is listed first and wins: an element carrying
          // both classes is chrome, and should not pay for three extra passes.
          if (selector === ".surface-glass" && element.matches(".surface-glass-chrome")) continue;
          paint(element, tier);
          resize.observe(element);
        }
      }
    };

    scan();
    // Dialogs and popovers mount on open, long after this effect ran.
    const added = new MutationObserver(() => {
      if (document.querySelector(`${SELECTOR}`)) scan();
    });
    added.observe(document.body, { childList: true, subtree: true });

    return () => {
      added.disconnect();
      resize.disconnect();
      host.remove();
      for (const element of document.querySelectorAll<HTMLElement>(`[${MARK}]`)) {
        element.style.backdropFilter = "";
        element.removeAttribute(MARK);
      }
    };
  }, []);

  return null;
}
