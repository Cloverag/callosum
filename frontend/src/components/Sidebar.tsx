"use client";

import Link from 'next/link';
import { Home, Users, FileText, Settings, Layers, Menu } from 'lucide-react';
import { useState } from 'react';

export default function Sidebar() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const navItems = [
    { name: 'Dashboard', icon: Home, href: '/dashboard' },
    { name: 'Meetings', icon: Users, href: '/meetings' },
    { name: 'Documents', icon: FileText, href: '/documents' },
    { name: 'Entity Conflicts', icon: Layers, href: '/entity-conflicts' },
    { name: 'Settings', icon: Settings, href: '/settings' },
  ];

  return (
    <div className={`${isCollapsed ? 'w-20' : 'w-64'} h-full glass-panel border-y-0 border-l-0 flex flex-col z-10 transition-all duration-300 relative`}>
      <div className={`p-6 flex items-center ${isCollapsed ? 'justify-center' : 'gap-3 justify-between'}`}>
        <div className="flex items-center gap-3 overflow-hidden">
          <div className="w-8 h-8 flex-shrink-0 rounded bg-primary flex items-center justify-center shadow-[0_0_15px_var(--color-glass-highlight)]">
            <Layers className="w-5 h-5 text-primary-foreground" />
          </div>
          {!isCollapsed && <span className="text-xl font-medium tracking-tight text-foreground text-glow whitespace-nowrap">Meridian</span>}
        </div>
        {!isCollapsed && (
          <button 
            onClick={() => setIsCollapsed(true)}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
          >
            <Menu className="w-4 h-4" />
          </button>
        )}
      </div>

      {isCollapsed && (
        <div className="flex justify-center pb-4">
          <button 
            onClick={() => setIsCollapsed(false)}
            className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>
        </div>
      )}
      
      <nav className={`flex-1 ${isCollapsed ? 'px-3' : 'px-4'} py-2 space-y-1 overflow-x-hidden`}>
        {navItems.map((item) => {
          const isActive = item.name === 'Entity Conflicts';
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center ${isCollapsed ? 'justify-center p-3' : 'gap-3 px-3 py-2.5'} rounded-lg transition-all duration-300 group ${
                isActive 
                  ? 'bg-primary/10 text-foreground shadow-[inset_0_1px_0_0_var(--color-glass-highlight)]' 
                  : 'text-muted-foreground hover:text-foreground hover:bg-black/5 dark:hover:bg-white/5'
              }`}
              title={isCollapsed ? item.name : undefined}
            >
              <item.icon className={`w-5 h-5 flex-shrink-0 transition-transform duration-300 ${isActive ? 'text-accent' : 'group-hover:scale-110'}`} />
              {!isCollapsed && <span className={`text-sm font-medium whitespace-nowrap ${isActive ? 'text-foreground' : ''}`}>{item.name}</span>}
            </Link>
          );
        })}
      </nav>

      <div className={`p-4 border-t border-glass-border ${isCollapsed ? 'flex justify-center px-2' : ''}`}>
        <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'gap-3 px-3'} py-2 w-full rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer overflow-hidden`} title={isCollapsed ? "Raj Malhotra" : undefined}>
          <div className="w-8 h-8 flex-shrink-0 rounded-full bg-card-bg border border-glass-border flex items-center justify-center">
            <span className="text-xs font-medium text-foreground">RM</span>
          </div>
          {!isCollapsed && (
            <div className="flex flex-col whitespace-nowrap">
              <span className="text-sm font-medium text-foreground">Raj Malhotra</span>
              <span className="text-xs text-muted-foreground">Board Member</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
