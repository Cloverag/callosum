import Icon from './Icon'

export default function MobileNav() {
  return (
    <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 bg-surface-container/80 backdrop-blur-xl border-t border-white/40 flex items-center justify-around z-50">
      <a href="#" className="flex flex-col items-center gap-1 text-primary">
        <Icon name="dashboard" fill />
        <span className="text-[10px] font-medium">Overview</span>
      </a>
      <a href="#" className="flex flex-col items-center gap-1 text-secondary">
        <Icon name="event" />
        <span className="text-[10px]">Meetings</span>
      </a>
      <button className="w-12 h-12 -mt-6 rounded-full bg-primary-container text-on-primary flex items-center justify-center shadow-lg border-4 border-surface" aria-label="Quick capture">
        <Icon name="add" />
      </button>
      <a href="#" className="flex flex-col items-center gap-1 text-secondary">
        <Icon name="auto_awesome" />
        <span className="text-[10px]">Copilot</span>
      </a>
      <a href="#" className="flex flex-col items-center gap-1 text-secondary">
        <Icon name="account_circle" />
        <span className="text-[10px]">Profile</span>
      </a>
    </nav>
  )
}
