"use client";

import { useCallback, useRef, type PointerEvent } from "react";

/**
 * Tracks the pointer across a focal surface so its sheen follows.
 *
 * Writes `--pointer-x` / `--pointer-y` straight onto the element rather than
 * holding them in state. A pointermove fires on nearly every frame, and routing
 * that through React would re-render the hero — and everything under it — dozens
 * of times a second to move a background. The CSS variable is the render.
 *
 * Mouse only. A touch "pointer" has no hover state to reveal the sheen, and
 * emitting coordinates for it would light the surface on tap and leave it lit;
 * a pen behaves the same way. `:hover` already gates the opacity, so this is
 * belt and braces on a device class that cannot use the effect anyway.
 *
 * Nothing here needs a reduced-motion branch: the surface reads the same
 * variables regardless, and `globals.css` decides whether the sheen moves.
 */
export function usePointerSheen<T extends HTMLElement>() {
  const ref = useRef<T>(null);

  const onPointerMove = useCallback((event: PointerEvent<T>) => {
    if (event.pointerType !== "mouse") return;
    const el = ref.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;

    el.style.setProperty("--pointer-x", `${((event.clientX - rect.left) / rect.width) * 100}%`);
    el.style.setProperty("--pointer-y", `${((event.clientY - rect.top) / rect.height) * 100}%`);
  }, []);

  /**
   * Returning to the centre on leave means the next hover starts from a neutral
   * position instead of wherever the pointer last exited, which otherwise reads
   * as the light having been left on.
   */
  const onPointerLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.removeProperty("--pointer-x");
    el.style.removeProperty("--pointer-y");
  }, []);

  return { ref, onPointerMove, onPointerLeave };
}
