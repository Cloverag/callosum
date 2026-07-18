"use client";

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navigation = [
  { name: 'Dashboard', href: '/dashboard' },
  { name: 'Meetings', href: '/meetings' },
  { name: 'Documents', href: '/documents' },
  { name: 'Entity Conflicts', href: '/entity-conflicts' },
  { name: 'Settings', href: '/settings' },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="flex h-full w-64 flex-col bg-[#051424] border-r border-[#273647]">
      <div className="flex h-16 shrink-0 items-center px-6 border-b border-[#273647]">
        <span className="text-xl font-bold tracking-tight text-[#d4e4fa]">Meridian</span>
      </div>
      <nav className="flex flex-1 flex-col px-4 py-6 space-y-2">
        {navigation.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`group flex items-center rounded-md px-3 py-2 text-sm font-medium ${
                isActive
                  ? 'bg-[#1E293B] text-white shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]'
                  : 'text-[#8691a7] hover:bg-[#122131] hover:text-[#d4e4fa]'
              }`}
            >
              {item.name}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
