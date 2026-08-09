"use client";

import * as React from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export type Theme = "light" | "dark" | "system";

export const THEME_KEY = "meridian.theme";

/**
 * Runs before first paint, from a <script> in <head>.
 *
 * Without it the document renders with the light tokens, then the stored choice
 * applies on hydration and the whole page flips — the flash of wrong theme. It
 * has to be inline and synchronous for that reason: any deferred or bundled
 * script is already too late.
 *
 * "system" deliberately writes NO attribute, so `prefers-color-scheme` decides.
 * Stamping `data-theme="light"` for it would freeze the page in light mode and
 * stop it following the OS, which is not what the user asked for.
 */
export const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t==="dark"||t==="light"){document.documentElement.setAttribute("data-theme",t)}}catch(e){}})()`;

function apply(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
  try {
    if (theme === "system") window.localStorage.removeItem(THEME_KEY);
    else window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* Private mode: the choice still applies for this page, it just will not persist. */
  }
}

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

/**
 * Three states, not two — "system" is a real choice and has to be reachable, or
 * a user who once pressed Dark can never get back to following their OS.
 *
 * A segmented control rather than a cycling icon button: with three states, a
 * single toggle makes you press it up to twice to reach a known one, and never
 * tells you which state you are in without decoding the icon.
 *
 * No transition on the swap. The theme is chrome the user changes deliberately
 * and rarely, and cross-fading thousands of elements is both expensive and the
 * kind of motion that reads as lag rather than polish.
 */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = React.useState<Theme>("system");

  React.useEffect(() => {
    try {
      const stored = window.localStorage.getItem(THEME_KEY);
      if (stored === "dark" || stored === "light") setTheme(stored);
    } catch {
      /* nothing stored is a valid state — "system" is already the default */
    }
  }, []);

  function choose(next: Theme) {
    setTheme(next);
    apply(next);
  }

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border border-border bg-surface-sunken p-0.5",
        className
      )}
    >
      {OPTIONS.map(({ value, label, icon: Icon }) => {
        const active = theme === value;
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => choose(value)}
            className={cn(
              "flex size-7 items-center justify-center rounded-full transition-colors duration-[--duration-hover]",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface-elevated",
              active
                ? "bg-surface-raised text-foreground shadow-card"
                : "text-subtle-foreground hover:text-foreground"
            )}
          >
            <Icon className="size-3.5" aria-hidden />
          </button>
        );
      })}
    </div>
  );
}
