// Semantic colour — meaning only.
// blue = actions · green = healthy/completed · amber = attention · red = critical
// (violet is Institutional Memory only and is applied directly there)

export const toneText = {
  success: 'text-success',
  warning: 'text-warning',
  error: 'text-error',
  neutral: 'text-secondary',
  primary: 'text-primary',
}

export const toneSoft = {
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  error: 'bg-error/10 text-error',
  neutral: 'bg-surface-container text-on-surface-variant',
  primary: 'bg-primary/10 text-primary',
}

// CSS variables for non-class contexts (SVG stroke, inline bar fills)
export const toneVar = {
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  error: 'var(--color-error)',
  neutral: 'var(--color-secondary)',
  primary: 'var(--color-primary-container)',
}
