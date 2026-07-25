import Icon from './Icon'
import { suggestedActions } from '../data'

// Copilot dock — persistent but visually quiet. Neutral glass, blue actions.
// (Violet is reserved for Institutional Memory, so it does not appear here.)
export default function AIWorkspace() {
  return (
    <aside className="hidden lg:flex fixed right-6 top-24 bottom-6 w-80 rounded-[24px] glass-dock flex-col p-4 z-50">
      <div className="flex items-center justify-between mb-5 px-1">
        <div className="flex items-center gap-2">
          <Icon name="auto_awesome" className="text-primary text-[20px]" />
          <div className="flex flex-col leading-tight">
            <h2 className="text-body-lg font-semibold text-on-surface">Copilot</h2>
            <span className="text-label-md text-secondary">Context aware</span>
          </div>
        </div>
        <button className="w-8 h-8 rounded-full hover:bg-white/60 flex items-center justify-center text-secondary transition-colors" aria-label="Collapse copilot">
          <Icon name="close_fullscreen" className="text-sm" />
        </button>
      </div>

      {/* Context awareness */}
      <div className="os-surface-quiet rounded-2xl p-4 mb-5">
        <p className="text-body-sm text-on-surface-variant text-pretty">
          You&rsquo;re preparing the Q4 board meeting. 2 unresolved items from the last session still need attention.
        </p>
        <button className="inline-flex items-center gap-1 text-primary text-label-md mt-2.5 hover:underline">
          View unresolved items
          <Icon name="arrow_forward" className="text-[14px]" />
        </button>
      </div>

      {/* Suggested */}
      <p className="text-label-md text-secondary mb-2 px-1">Suggested</p>
      <div className="flex flex-col gap-2 flex-1">
        {suggestedActions.map((action) => (
          <button
            key={action}
            className="text-left px-3.5 py-2.5 rounded-xl os-surface-quiet hover:bg-white text-body-sm text-on-surface flex items-center justify-between group transition-colors"
          >
            {action}
            <Icon name="arrow_forward" className="text-sm text-secondary opacity-0 group-hover:opacity-100 transition-opacity" />
          </button>
        ))}
      </div>

      {/* Composer */}
      <div className="mt-4 relative">
        <input
          type="text"
          aria-label="Ask Meridian Copilot"
          placeholder="Ask Meridian…"
          className="w-full bg-white/60 border border-hairline rounded-xl py-2.5 pl-3.5 pr-11 text-body-sm text-on-surface placeholder:text-secondary focus:border-primary focus:bg-white focus:outline-none transition-all"
        />
        <button className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-lg bg-primary-container text-on-primary flex items-center justify-center hover:shadow-md transition-shadow" aria-label="Send">
          <Icon name="arrow_upward" className="text-[16px]" />
        </button>
      </div>
    </aside>
  )
}
