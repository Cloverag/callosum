/**
 * Material Symbols (Outlined) icon.
 * `fill` renders the filled variant; `className` controls size/color via Tailwind.
 */
export default function Icon({ name, className = '', fill = false, style }) {
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{
        ...(fill ? { fontVariationSettings: "'FILL' 1" } : null),
        ...style,
      }}
      aria-hidden="true"
    >
      {name}
    </span>
  )
}
