'use client';
import { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, AlertTriangle, BarChart3, Settings, Menu, X, Shield } from 'lucide-react';
import clsx from 'clsx';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { href: '/incidents', label: 'Incidents', icon: AlertTriangle },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        className="fixed top-4 left-4 z-50 md:hidden bg-sidebar text-white p-2 rounded-lg"
        onClick={() => setOpen(!open)}
      >
        {open ? <X size={20} /> : <Menu size={20} />}
      </button>

      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 w-64 bg-sidebar text-white flex flex-col transition-transform duration-200',
          'md:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <Link href="/" className="flex items-center gap-3 px-6 py-6 border-b border-white/10">
          <Shield className="text-coral" size={28} />
          <span className="font-serif text-xl">Incident Copilot</span>
        </Link>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={() => setOpen(false)}
              className={clsx(
                'flex items-center gap-3 px-4 py-3 rounded-lg text-sm font-medium transition-colors',
                pathname.startsWith(href)
                  ? 'bg-coral text-white'
                  : 'text-gray-300 hover:bg-sidebar-hover hover:text-white'
              )}
            >
              <Icon size={18} />
              {label}
            </Link>
          ))}
        </nav>

        <div className="px-6 py-4 border-t border-white/10 text-xs text-gray-400">
          v1.0 · Copilot Engine
        </div>
      </aside>

      {open && (
        <div className="fixed inset-0 bg-black/50 z-30 md:hidden" onClick={() => setOpen(false)} />
      )}
    </>
  );
}
