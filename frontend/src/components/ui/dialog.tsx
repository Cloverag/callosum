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
        "surface-glass m-auto w-[calc(100%-2rem)] max-w-lg rounded-[20px] p-0 text-foreground",
        "backdrop:bg-black/40 backdrop:backdrop-blur-sm",
        className
      )}
    >
      <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-5">
        <div className="min-w-0">
          <h2 id="dialog-title" className="text-lg font-semibold tracking-tight text-foreground">
            {title}
          </h2>
          {description && <div className="mt-0.5 text-sm text-muted-foreground">{description}</div>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="-mr-1 flex size-8 shrink-0 items-center justify-center rounded-[10px] text-muted-foreground transition-colors duration-150 hover:bg-surface-sunken hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
        >
          <X className="size-4" />
        </button>
      </div>

      {children && <div className="px-6 py-5">{children}</div>}
      {footer && <div className="flex items-center justify-end gap-2 border-t border-border px-6 py-5">{footer}</div>}
    </dialog>
  );
}
