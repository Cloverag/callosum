"use client";

import { Bell, Search, Layers, ChevronRight } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';
import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { apiClient } from '@/lib/api';

export default function Header() {
  const [showNotifications, setShowNotifications] = useState(false);
  const [conflictCount, setConflictCount] = useState<number>(0);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Fetch conflict count (getConflicts returns the full array; count pending client-side)
    apiClient.getConflicts().then((all) => {
      setConflictCount(all.filter((c) => c.status === 'pending').length);
    });

    // Handle outside click
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="h-16 glass-panel border-x-0 border-t-0 flex items-center justify-between px-8 z-20 relative">
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
        
        {/* Notifications Dropdown */}
        <div className="relative" ref={dropdownRef}>
          <button 
            onClick={() => setShowNotifications(!showNotifications)}
            className="relative p-2 text-muted-foreground hover:text-foreground transition-colors rounded-full hover:bg-black/5 dark:hover:bg-white/10"
          >
            <Bell className="w-5 h-5" />
            {conflictCount > 0 && (
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-accent shadow-[0_0_8px_var(--color-accent-glow)]"></span>
            )}
          </button>

          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 glass-panel rounded-xl shadow-2xl border border-glass-border overflow-hidden animate-in fade-in slide-in-from-top-2 duration-200 z-50">
              <div className="p-4 border-b border-glass-border flex items-center justify-between">
                <h3 className="font-medium text-foreground">Notifications</h3>
                {conflictCount > 0 && (
                  <span className="bg-accent/20 text-accent text-xs px-2 py-0.5 rounded-full">{conflictCount} New</span>
                )}
              </div>
              <div className="max-h-96 overflow-y-auto">
                {conflictCount > 0 ? (
                  <Link 
                    href="/entity-conflicts"
                    onClick={() => setShowNotifications(false)}
                    className="flex items-start gap-3 p-4 hover:bg-black/5 dark:hover:bg-white/5 transition-colors border-b border-glass-border/50 group"
                  >
                    <div className="w-8 h-8 rounded-full bg-accent/10 flex flex-shrink-0 items-center justify-center mt-0.5">
                      <Layers className="w-4 h-4 text-accent" />
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-foreground">Entity Conflicts Need Attention</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        There are {conflictCount} potential duplicate entities waiting for your review.
                      </p>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                  </Link>
                ) : (
                  <div className="p-8 text-center text-muted-foreground flex flex-col items-center">
                    <Bell className="w-8 h-8 opacity-20 mb-3" />
                    <p className="text-sm">You're all caught up!</p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
