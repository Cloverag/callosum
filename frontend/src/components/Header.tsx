import { Bell, Search } from 'lucide-react';

export default function Header() {
  return (
    <header className="h-16 glass-panel border-x-0 border-t-0 flex items-center justify-between px-8 z-10">
      <div className="flex items-center gap-4 text-sm">
        <span className="text-neutral-400">Workspace</span>
        <span className="text-neutral-600">/</span>
        <span className="font-medium text-white text-glow">Acme Corp</span>
        <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-blue-500/10 text-blue-400 border border-blue-500/20 uppercase">
          Series B
        </span>
      </div>
      
      <div className="flex items-center gap-4">
        <div className="relative group">
          <Search className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2 group-focus-within:text-white transition-colors" />
          <input 
            type="text" 
            placeholder="Search workspace..." 
            className="bg-black/50 border border-[rgba(255,255,255,0.1)] rounded-full pl-9 pr-4 py-1.5 text-sm text-white placeholder:text-neutral-500 focus:outline-none focus:border-[rgba(255,255,255,0.3)] focus:ring-1 focus:ring-white/10 transition-all w-64"
          />
        </div>
        <button className="relative p-2 text-neutral-400 hover:text-white transition-colors">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.8)]"></span>
        </button>
      </div>
    </header>
  );
}
