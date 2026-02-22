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
        'hidden md:flex flex-col border-r bg-card transition-all duration-300',
        sidebarOpen ? 'w-64' : 'w-16'
      )}
    >
      {/* Logo */}
      <div className="flex h-16 items-center justify-between border-b px-4">
        {sidebarOpen && (
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <AlertTriangle className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="font-semibold">Incident Copilot</span>
          </Link>
        )}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleSidebar}
          className={cn(!sidebarOpen && 'mx-auto')}
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

        <Separator className="my-4" />

        <div className="space-y-1">
          {sidebarOpen && (
            <p className="px-3 py-2 text-xs font-semibold uppercase text-muted-foreground">
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
      <div className="border-t p-2">
        {bottomNavItems.map((item) => (
          <NavItem
            key={item.href}
            {...item}
            isActive={pathname === item.href}
            collapsed={!sidebarOpen}
          />
        ))}
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
      <aside className="fixed inset-y-0 left-0 flex w-72 flex-col bg-card shadow-xl animate-in slide-in-from-left duration-300">
        {/* Header with close button */}
        <div className="flex h-16 items-center justify-between border-b px-4">
          <Link
            href="/dashboard"
            className="flex items-center gap-2"
            onClick={() => setMobileSidebarOpen(false)}
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary">
              <AlertTriangle className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="font-semibold">Incident Copilot</span>
          </Link>
          <Button
            variant="ghost"
            size="icon"
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

          <Separator className="my-4" />

          <div className="space-y-1">
            <p className="px-3 py-2 text-xs font-semibold uppercase text-muted-foreground">
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
        <div className="border-t p-2">
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
          ? 'bg-primary text-primary-foreground'
          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
        collapsed && 'justify-center'
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
          : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
      )}
    >
      <Icon className="h-5 w-5 shrink-0" />
      <span>{label}</span>
    </Link>
  );
}
