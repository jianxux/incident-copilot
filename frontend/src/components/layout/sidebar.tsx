'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { useAppStore } from '@/lib/store';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  AlertTriangle,
  BarChart3,
  Bell,
  BookOpen,
  Calendar,
  ChevronLeft,
  ChevronRight,
  ChevronsRight,
  Home,
  Layers,
  LifeBuoy,
  Settings,
  Shield,
  Users,
  X,
  Zap,
} from 'lucide-react';

const mainNavItems = [
  { href: '/dashboard', label: 'Dashboard', icon: Home },
  { href: '/incidents', label: 'Incidents', icon: AlertTriangle },
  { href: '/analytics', label: 'Analytics', icon: BarChart3 },
  { href: '/insights', label: 'AI Insights', icon: Zap },
  { href: '/timeline', label: 'Timeline', icon: Calendar },
];

const secondaryNavItems = [
  { href: '/services', label: 'Services', icon: Layers },
  { href: '/runbooks', label: 'Runbooks', icon: BookOpen },
  { href: '/on-call', label: 'On-Call', icon: Users },
  { href: '/alerts', label: 'Alerts', icon: Bell },
];

const bottomNavItems = [
  { href: '/integrations', label: 'Integrations', icon: Shield },
  { href: '/settings', label: 'Settings', icon: Settings },
  { href: '/support', label: 'Support', icon: LifeBuoy },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar } = useAppStore();

  return (
    <aside
      className={cn(
        'hidden md:flex flex-col border-r border-[#2a2420] bg-[#1a1614] transition-all duration-300',
        sidebarOpen ? 'w-64' : 'w-16'
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          'relative flex h-16 items-center border-b border-[#2a2420]',
          sidebarOpen ? 'justify-between px-4' : 'justify-center px-2'
        )}
      >
        <Link href="/dashboard" className={cn('flex items-center', sidebarOpen && 'gap-2')}>
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
            <AlertTriangle className="h-5 w-5 text-primary-foreground" />
          </div>
          {sidebarOpen && <span className="font-semibold text-[#f5efe8]">Incident Copilot</span>}
        </Link>
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          className={cn(
            'text-[#a8998a] hover:bg-[#2a2420] hover:text-[#e8ddd0]',
            !sidebarOpen && 'absolute right-2 bg-[#2a2420] hover:bg-[#332c27]'
          )}
        >
          {sidebarOpen ? (
            <ChevronLeft className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 p-2">
        <div className="space-y-1">
          {mainNavItems.map((item) => (
            <NavItem
              key={item.href}
              {...item}
              isActive={pathname === item.href}
              collapsed={!sidebarOpen}
            />
          ))}
        </div>

        <Separator className="my-4 bg-[#2a2420]" />

        <div className="space-y-1">
          {sidebarOpen && (
            <p className="px-3 py-2 text-xs font-semibold uppercase text-[#6b5e52]">
              Operations
            </p>
          )}
          {secondaryNavItems.map((item) => (
            <NavItem
              key={item.href}
              {...item}
              isActive={pathname === item.href}
              collapsed={!sidebarOpen}
            />
          ))}
        </div>
      </nav>

      {/* Bottom nav */}
      <div className="border-t border-[#2a2420] p-2">
        {bottomNavItems.map((item) => (
          <NavItem
            key={item.href}
            {...item}
            isActive={pathname === item.href}
            collapsed={!sidebarOpen}
          />
        ))}
        {!sidebarOpen && (
          <div className="flex justify-center py-3 border-t border-[#2a2420]">
            <button
              onClick={toggleSidebar}
              className="text-[#6b5e52] hover:text-[#a8998a] transition-colors"
            >
              <ChevronsRight className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}

export function MobileSidebar() {
  const pathname = usePathname();
  const { mobileSidebarOpen, setMobileSidebarOpen } = useAppStore();

  if (!mobileSidebarOpen) return null;

  return (
    <div className="fixed inset-0 z-50 md:hidden">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50"
        onClick={() => setMobileSidebarOpen(false)}
      />

      {/* Sidebar panel */}
      <aside className="fixed inset-y-0 left-0 flex w-72 flex-col border-r border-[#2a2420] bg-[#1a1614] shadow-xl animate-in slide-in-from-left duration-300">
        {/* Header with close button */}
        <div className="flex h-16 items-center justify-between border-b border-[#2a2420] px-4">
          <Link
            href="/dashboard"
            className="flex items-center gap-2"
            onClick={() => setMobileSidebarOpen(false)}
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <AlertTriangle className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="font-semibold text-[#f5efe8]">Incident Copilot</span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
            className="text-[#a8998a] hover:bg-[#2a2420] hover:text-[#e8ddd0]"
            onClick={() => setMobileSidebarOpen(false)}
          >
            <X className="h-5 w-5" />
          </Button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-1 overflow-y-auto p-2">
          <div className="space-y-1">
            {mainNavItems.map((item) => (
              <MobileNavItem
                key={item.href}
                {...item}
                isActive={pathname === item.href}
                onNavigate={() => setMobileSidebarOpen(false)}
              />
            ))}
          </div>

          <Separator className="my-4 bg-[#2a2420]" />

          <div className="space-y-1">
            <p className="px-3 py-2 text-xs font-semibold uppercase text-[#6b5e52]">
              Operations
            </p>
            {secondaryNavItems.map((item) => (
              <MobileNavItem
                key={item.href}
                {...item}
                isActive={pathname === item.href}
                onNavigate={() => setMobileSidebarOpen(false)}
              />
            ))}
          </div>
        </nav>

        {/* Bottom nav */}
        <div className="border-t border-[#2a2420] p-2">
          {bottomNavItems.map((item) => (
            <MobileNavItem
              key={item.href}
              {...item}
              isActive={pathname === item.href}
              onNavigate={() => setMobileSidebarOpen(false)}
            />
          ))}
        </div>
      </aside>
    </div>
  );
}

interface NavItemProps {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  isActive: boolean;
  collapsed: boolean;
}

function NavItem({ href, label, icon: Icon, isActive, collapsed }: NavItemProps) {
  return (
    <Link
      href={href}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
        isActive
          ? collapsed
            ? 'bg-primary/15 text-primary'
            : 'bg-primary text-primary-foreground'
          : 'text-[#a8998a] hover:bg-[#2a2420] hover:text-[#e8ddd0]',
        collapsed && 'px-0 justify-center'
      )}
      title={collapsed ? label : undefined}
    >
      <Icon className="h-5 w-5 shrink-0" />
      {!collapsed && <span>{label}</span>}
    </Link>
  );
}

interface MobileNavItemProps {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  isActive: boolean;
  onNavigate: () => void;
}

function MobileNavItem({ href, label, icon: Icon, isActive, onNavigate }: MobileNavItemProps) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      className={cn(
        'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
        isActive
          ? 'bg-primary text-primary-foreground'
          : 'text-[#a8998a] hover:bg-[#2a2420] hover:text-[#e8ddd0]'
      )}
    >
      <Icon className="h-5 w-5 shrink-0" />
      <span>{label}</span>
    </Link>
  );
}
