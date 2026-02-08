'use client';

import { useTheme } from 'next-themes';
import { useAppStore } from '@/lib/store';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Bell,
  LogOut,
  Moon,
  Search,
  Settings,
  Sun,
  User,
  Wifi,
  WifiOff,
} from 'lucide-react';

export function Header() {
  const { theme, setTheme } = useTheme();
  const { user, realTimeEnabled, setRealTimeEnabled } = useAppStore();

  return (
    <header className="flex h-16 items-center justify-between border-b bg-card px-6">
      {/* Search */}
      <div className="relative w-96">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search incidents, services, runbooks..."
          className="pl-10"
        />
      </div>

      {/* Right side */}
      <div className="flex items-center gap-4">
        {/* Real-time toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setRealTimeEnabled(!realTimeEnabled)}
          title={realTimeEnabled ? 'Real-time updates on' : 'Real-time updates off'}
        >
          {realTimeEnabled ? (
            <Wifi className="h-5 w-5 text-green-500" />
          ) : (
            <WifiOff className="h-5 w-5 text-muted-foreground" />
          )}
        </Button>

        {/* Theme toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        >
          <Sun className="h-5 w-5 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-5 w-5 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>

        {/* Notifications */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className="relative">
              <Bell className="h-5 w-5" />
              <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
                3
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-80">
            <DropdownMenuLabel>Notifications</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="flex flex-col items-start gap-1 p-3">
              <div className="flex items-center gap-2">
                <Badge variant="critical" className="text-xs">Critical</Badge>
                <span className="text-xs text-muted-foreground">2m ago</span>
              </div>
              <p className="text-sm font-medium">Database connection pool exhausted</p>
              <p className="text-xs text-muted-foreground">payment-service</p>
            </DropdownMenuItem>
            <DropdownMenuItem className="flex flex-col items-start gap-1 p-3">
              <div className="flex items-center gap-2">
                <Badge variant="high" className="text-xs">High</Badge>
                <span className="text-xs text-muted-foreground">15m ago</span>
              </div>
              <p className="text-sm font-medium">API latency spike detected</p>
              <p className="text-xs text-muted-foreground">api-gateway</p>
            </DropdownMenuItem>
            <DropdownMenuItem className="flex flex-col items-start gap-1 p-3">
              <div className="flex items-center gap-2">
                <Badge variant="info" className="text-xs">Info</Badge>
                <span className="text-xs text-muted-foreground">1h ago</span>
              </div>
              <p className="text-sm font-medium">Deployment completed successfully</p>
              <p className="text-xs text-muted-foreground">user-service</p>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="justify-center text-primary">
              View all notifications
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* User menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary">
                <User className="h-4 w-4 text-primary-foreground" />
              </div>
              <span className="hidden md:inline">{user?.name || 'User'}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>My Account</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>
              <User className="mr-2 h-4 w-4" />
              Profile
            </DropdownMenuItem>
            <DropdownMenuItem>
              <Settings className="mr-2 h-4 w-4" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-red-500">
              <LogOut className="mr-2 h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
