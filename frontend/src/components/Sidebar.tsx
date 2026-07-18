import Link from 'next/link';
import { Home, Users, FileText, Settings, Layers } from 'lucide-react';

export default function Sidebar() {
  const navItems = [
    { name: 'Dashboard', icon: Home, href: '/dashboard' },
    { name: 'Meetings', icon: Users, href: '/meetings' },
    { name: 'Documents', icon: FileText, href: '/documents' },
    { name: 'Entity Conflicts', icon: Layers, href: '/entity-conflicts' },
    { name: 'Settings', icon: Settings, href: '/settings' },
  ];

  return (
    <div className="w-64 h-full glass-panel border-y-0 border-l-0 flex flex-col z-10">
      <div className="p-6 flex items-center gap-3">
        <div className="w-8 h-8 rounded bg-white flex items-center justify-center shadow-[0_0_15px_rgba(255,255,255,0.4)]">
          <Layers className="w-5 h-5 text-black" />
        </div>
        <span className="text-xl font-medium tracking-tight text-white text-glow">Meridian</span>
      </div>
      
      <nav className="flex-1 px-4 py-6 space-y-1">
        {navItems.map((item) => {
          const isActive = item.name === 'Entity Conflicts';
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-300 group ${
                isActive 
                  ? 'bg-white/10 text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]' 
                  : 'text-neutral-400 hover:text-white hover:bg-white/5'
              }`}
            >
              <item.icon className={`w-5 h-5 transition-transform duration-300 ${isActive ? 'text-blue-400' : 'group-hover:scale-110'}`} />
              <span className={`text-sm font-medium ${isActive ? 'text-white' : ''}`}>{item.name}</span>
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-[rgba(255,255,255,0.1)]">
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="w-8 h-8 rounded-full bg-neutral-800 border border-neutral-700 flex items-center justify-center">
            <span className="text-xs font-medium text-neutral-300">RM</span>
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-medium text-white">Raj Malhotra</span>
            <span className="text-xs text-neutral-500">Board Member</span>
          </div>
        </div>
      </div>
    </div>
  );
}
