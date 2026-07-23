import Icon from './Icon'
import { sideNav } from '../data'

export default function Sidebar() {
  return (
    <nav className="hidden md:flex fixed left-6 top-6 bottom-6 w-[260px] rounded-[22px] border-l border-t border-white/55 bg-surface-container/60 backdrop-blur-xl shadow-[0_8px_32px_rgba(15,23,42,0.08)] flex-col p-4 z-40">
      {/* Brand */}
      <div className="flex items-center gap-3 px-2 mb-8 mt-2">
        <div className="w-10 h-10 rounded-xl bg-primary-container text-on-primary flex items-center justify-center font-bold text-lg shadow-sm">
          M
        </div>
        <div>
          <h2 className="text-title-md font-bold text-primary leading-tight">Meridian OS</h2>
          <p className="text-label-md text-secondary">Executive Suite</p>
        </div>
      </div>

      {/* Primary nav */}
      <div className="flex flex-col gap-1 flex-1">
        {sideNav.map((item) => (
          <a
            key={item.label}
            href="#"
            className={
              item.active
                ? 'flex items-center gap-3 px-3 py-2.5 rounded-xl bg-primary/10 text-primary shadow-[inset_0_0_10px_rgba(37,99,235,0.1)] active:scale-95 transition-all duration-200'
                : 'flex items-center gap-3 px-3 py-2.5 rounded-xl text-secondary hover:text-primary hover:bg-white/10 active:scale-95 transition-all duration-200'
            }
          >
            <div
              className={
                item.active
                  ? 'w-10 h-10 rounded-[10px] bg-primary/10 flex items-center justify-center'
                  : 'w-10 h-10 rounded-[10px] flex items-center justify-center'
              }
            >
              <Icon name={item.icon} fill={item.active} />
            </div>
            <span className="text-body-sm font-medium">{item.label}</span>
          </a>
        ))}
      </div>

      <button className="mt-4 mb-4 flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-primary-container text-on-primary text-button shadow-md hover:shadow-lg transition-shadow">
        <Icon name="add" className="text-sm" />
        New Initiative
      </button>

      <div className="pt-4 border-t border-white/30 flex flex-col gap-1">
        <a href="#" className="flex items-center gap-3 px-3 py-2 rounded-xl text-secondary hover:text-primary hover:bg-white/10 transition-colors">
          <Icon name="help" className="text-sm" />
          <span className="text-body-sm">Support</span>
        </a>
        <a href="#" className="flex items-center gap-3 px-3 py-2 rounded-xl text-secondary hover:text-primary hover:bg-white/10 transition-colors">
          <Icon name="inventory_2" className="text-sm" />
          <span className="text-body-sm">Archive</span>
        </a>
      </div>
    </nav>
  )
}
