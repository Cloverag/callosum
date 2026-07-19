import { Bell, Search } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

export default function Header() {
  return (
    <header className="h-16 glass-panel border-x-0 border-t-0 flex items-center justify-between px-8 z-10">
      <div className="flex items-center gap-4 text-sm">
        <span className="text-muted-foreground">Workspace</span>
        <span className="text-border-hover">/</span>
        <span className="font-medium text-foreground text-glow">Acme Corp</span>
        <span className="px-2 py-0.5 rounded text-[10px] font-bold tracking-wider bg-accent/10 text-accent border border-accent/20 uppercase">
          Series B
        </span>
      </div>
      
      <div className="flex items-center gap-4">
        <div className="relative group">
          <Search className="w-4 h-4 text-muted-foreground absolute left-3 top-1/2 -translate-y-1/2 group-focus-within:text-foreground transition-colors" />
          <input 
            type="text" 
            placeholder="Search workspace..." 
            className="bg-card-bg border border-glass-border rounded-full pl-9 pr-4 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-glass-highlight focus:ring-1 focus:ring-glass-highlight transition-all w-64"
          />
        </div>
        <ThemeToggle />
        <button className="relative p-2 text-muted-foreground hover:text-foreground transition-colors rounded-full hover:bg-black/5 dark:hover:bg-white/10">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_var(--color-accent-glow)]"></span>
        </button>
      </div>
    </header>
  );
}
