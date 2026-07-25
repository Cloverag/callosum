/**
 * Quiet section grouping — a calm but confident header + content, separated by
 * space and typography rather than a heavy card. Larger title, no eyebrow.
 */
export default function Section({ title, action, children, className = '' }) {
  return (
    <section className={className}>
      {title && (
        <div className="flex items-center justify-between gap-4 mb-4">
          <h2 className="text-[1.375rem] leading-tight font-semibold tracking-[-0.01em] text-on-surface">
            {title}
          </h2>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}
