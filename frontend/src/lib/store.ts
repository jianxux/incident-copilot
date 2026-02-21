import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { IncidentFilter, Severity, Status } from '@/types/incident';

interface User {
  id: string;
  name: string;
  email: string;
  avatar_url?: string;
  role: string;
  teams: string[];
}

interface AppState {
  // User
  user: User | null;
  setUser: (user: User | null) => void;
  
  // Theme
  theme: 'light' | 'dark' | 'system';
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
  
  // Sidebar
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  // Mobile sidebar
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  toggleMobileSidebar: () => void;
  
  // Filters
  incidentFilters: IncidentFilter;
  setIncidentFilters: (filters: IncidentFilter) => void;
  resetFilters: () => void;
  
  // Notifications
  notificationsEnabled: boolean;
  setNotificationsEnabled: (enabled: boolean) => void;
  soundEnabled: boolean;
  setSoundEnabled: (enabled: boolean) => void;
  
  // View preferences
  incidentView: 'list' | 'grid' | 'timeline';
  setIncidentView: (view: 'list' | 'grid' | 'timeline') => void;
  
  // Real-time
  realTimeEnabled: boolean;
  setRealTimeEnabled: (enabled: boolean) => void;
}

const defaultFilters: IncidentFilter = {
  status: undefined,
  severity: undefined,
  service: undefined,
  team: undefined,
};

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // User
      user: null,
      setUser: (user) => set({ user }),
      
      // Theme
      theme: 'dark',
      setTheme: (theme) => set({ theme }),
      
      // Sidebar
      sidebarOpen: true,
      setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

      // Mobile sidebar
      mobileSidebarOpen: false,
      setMobileSidebarOpen: (mobileSidebarOpen) => set({ mobileSidebarOpen }),
      toggleMobileSidebar: () => set((state) => ({ mobileSidebarOpen: !state.mobileSidebarOpen })),
      
      // Filters
      incidentFilters: defaultFilters,
      setIncidentFilters: (filters) => set({ incidentFilters: filters }),
      resetFilters: () => set({ incidentFilters: defaultFilters }),
      
      // Notifications
      notificationsEnabled: true,
      setNotificationsEnabled: (enabled) => set({ notificationsEnabled: enabled }),
      soundEnabled: true,
      setSoundEnabled: (enabled) => set({ soundEnabled: enabled }),
      
      // View preferences
      incidentView: 'list',
      setIncidentView: (view) => set({ incidentView: view }),
      
      // Real-time
      realTimeEnabled: true,
      setRealTimeEnabled: (enabled) => set({ realTimeEnabled: enabled }),
    }),
    {
      name: 'incident-copilot-store',
      partialize: (state) => ({
        theme: state.theme,
        sidebarOpen: state.sidebarOpen,
        notificationsEnabled: state.notificationsEnabled,
        soundEnabled: state.soundEnabled,
        incidentView: state.incidentView,
        realTimeEnabled: state.realTimeEnabled,
      }),
    }
  )
);
