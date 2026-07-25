import Icon from './Icon'

export default function TopBar() {
  return (
    <header className="hidden md:flex fixed top-6 left-[300px] right-6 h-16 rounded-xl border-l border-t border-white/55 bg-surface/30 backdrop-blur-md shadow-sm items-center justify-between px-6 z-40 transition-all duration-300">
      <div className="flex items-center">
        <span className="text-headline-lg font-black tracking-tight text-primary">Meridian</span>
      </div>

      <div className="flex items-center gap-4">
        <div className="relative hidden lg:block">
          <Icon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary text-sm" />
          <input
            type="text"
            aria-label="Search across Meridian"
            placeholder="Search across Meridian..."
            className="w-64 pl-10 pr-16 py-2 rounded-xl bg-white/40 border border-white/55 focus:border-primary focus:bg-white/60 focus:outline-none transition-all text-body-sm text-on-surface placeholder:text-secondary"
          />
          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-label-md text-secondary border border-secondary/20 rounded px-1.5 py-0.5 bg-white/30">
            ⌘K
          </span>
        </div>

        <button className="w-10 h-10 rounded-full hover:bg-white/20 flex items-center justify-center text-on-surface transition-colors relative" aria-label="Notifications">
          <Icon name="notifications" />
          <span className="absolute top-2 right-2.5 w-2 h-2 bg-error rounded-full border border-surface"></span>
        </button>
        <button className="w-10 h-10 rounded-full hover:bg-white/20 flex items-center justify-center text-on-surface transition-colors" aria-label="Account">
          <Icon name="account_circle" />
        </button>
      </div>
    </header>
  )
}
