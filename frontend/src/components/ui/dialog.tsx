"use client";

import * as React from "react";
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
 * Modal built on the native <dialog> element: focus is trapped, Escape closes,
 * and the background is made inert by the platform — no hand-rolled focus trap.
 */
export function Dialog({ open, onClose, title, description, children, footer, className }: DialogProps) {
  const ref = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  // Backdrop click: with showModal(), a click on the ::backdrop targets the dialog itself.
  const onBackdropClick = (e: React.MouseEvent<HTMLDialogElement>) => {
    if (e.target === ref.current) onClose();
  };

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={onBackdropClick}
      aria-labelledby="dialog-title"
      className={cn(
        "m-auto w-[calc(100%-2rem)] max-w-lg rounded-xl border border-border bg-surface-raised p-0 text-foreground shadow-2xl",
        "backdrop:bg-black/50 backdrop:backdrop-blur-sm",
        className
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h2 id="dialog-title" className="text-lg font-medium tracking-tight text-foreground">
            {title}
          </h2>
          {description && <div className="mt-0.5 text-sm text-muted-foreground">{description}</div>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mr-1 flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors duration-150 hover:bg-surface-elevated hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <X className="size-4" />
        </button>
      </div>

      {children && <div className="px-5 py-4">{children}</div>}
      {footer && <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">{footer}</div>}
    </dialog>
  );
}
