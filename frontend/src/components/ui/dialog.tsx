"use client";

import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

/**
 * Modal built on Base UI's Dialog: focus is trapped, Escape and backdrop clicks
 * close, and the rest of the page is made inert by the primitive.
 *
 * This replaced a native `<dialog>` implementation, which was correct about
 * focus but wrong about labelling: it hardcoded `id="dialog-title"` and pointed
 * `aria-labelledby` at that literal. The calendar mounts two dialogs
 * (`meeting-detail`, `meeting-form`), so the id was not unique and a screen
 * reader could resolve the accessible name to the wrong heading. Base UI wires
 * `aria-labelledby` / `aria-describedby` to the Title and Description parts with
 * generated ids, so the defect is structurally impossible here rather than
 * fixed by hand.
 */
export function Dialog({ open, onClose, title, description, children, footer, className }: DialogProps) {
  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          className={cn(
            "fixed inset-0 z-50 bg-black/40 backdrop-blur-sm",
            "transition-opacity duration-(--duration-state) ease-(--ease-out-quart)",
            "data-starting-style:opacity-0 data-ending-style:opacity-0"
          )}
        />
        <DialogPrimitive.Popup
          className={cn(
            // Level 3 — floating UI. The only surfaces that leave the page
            // plane (DESIGN.md — Elevation).
            "surface-glass fixed top-1/2 left-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2",
            "rounded-[20px] p-0 text-foreground outline-none",
            "transition-[opacity,transform] duration-(--duration-state) ease-(--ease-out-quart)",
            "data-starting-style:scale-95 data-starting-style:opacity-0",
            "data-ending-style:scale-95 data-ending-style:opacity-0",
            className
          )}
        >
          <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
            <div className="min-w-0">
              <DialogPrimitive.Title className="text-lg font-semibold tracking-tight text-foreground">
                {title}
              </DialogPrimitive.Title>
              {description && (
                <DialogPrimitive.Description
                  render={<div />}
                  className="mt-0.5 text-sm text-muted-foreground"
                >
                  {description}
                </DialogPrimitive.Description>
              )}
            </div>
            <DialogPrimitive.Close
              aria-label="Close"
              className="-mr-1 flex size-8 shrink-0 items-center justify-center rounded-[10px] text-muted-foreground transition-colors duration-(--duration-hover) hover:bg-surface-sunken hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
            >
              <X className="size-4" />
            </DialogPrimitive.Close>
          </div>

          {children && <div className="px-6 py-5">{children}</div>}
          {footer && (
            <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-5">{footer}</div>
          )}
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
