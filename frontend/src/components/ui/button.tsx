"use client";

import * as React from "react";
import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Meridian's button, on Base UI's Button primitive.
 *
 * The variant NAMES are Meridian's, not shadcn's, and deliberately so: this is
 * the design system, and `primary | secondary | ghost | danger` is the
 * vocabulary DESIGN.md §5 uses and that 45 call sites already pass. shadcn's
 * `default | outline | destructive` would say the same thing in a language the
 * brief does not speak.
 *
 * What the primitive buys over a bare `<button>`: `render` polymorphism (a
 * button that needs to be a link stops being a div with a click handler), and
 * Base UI's disabled handling, which keeps a disabled control focusable so it
 * can still be discovered by a screen reader.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-[12px] font-medium whitespace-nowrap select-none " +
    "transition-[color,background-color,border-color,box-shadow] duration-[--duration-hover] ease-out " +
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 focus-visible:ring-offset-surface " +
    "disabled:pointer-events-none disabled:opacity-50 " +
    // Icons size themselves unless a call site says otherwise.
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        // Primary is the ONE dominant action per surface — solid blue.
        primary: "bg-accent text-accent-foreground shadow-card hover:bg-accent-hover active:translate-y-px",
        // Secondary — white with a gray border (brief: "Secondary: White + gray border").
        secondary:
          "bg-surface-raised text-foreground border border-border shadow-card hover:border-border-strong hover:bg-surface-alt",
        ghost: "bg-transparent text-muted-foreground hover:text-foreground hover:bg-surface-sunken",
        danger: "bg-danger text-danger-foreground shadow-card hover:bg-danger-emphasis active:translate-y-px",
      },
      size: {
        sm: "h-8 px-3.5 text-[13px]",
        md: "h-10 px-5 text-sm",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends Omit<React.ComponentProps<typeof ButtonPrimitive>, "className">,
    VariantProps<typeof buttonVariants> {
  className?: string;
  loading?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading = false, disabled, children, ...props }, ref) => (
    <ButtonPrimitive
      ref={ref}
      data-slot="button"
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </ButtonPrimitive>
  )
);
Button.displayName = "Button";

export { buttonVariants };
