import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api';

export function useAnalyticsSummary(period: 'day' | 'week' | 'month' | 'quarter' = 'week') {
  return useQuery({
    queryKey: ['analytics-summary', period],
    queryFn: () => analyticsApi.getSummary(period),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useInsights() {
  return useQuery({
    queryKey: ['insights'],
    queryFn: () => analyticsApi.getInsights(),
    refetchInterval: 5 * 60 * 1000, // Refetch every 5 minutes
  });
}

export function useMTTR(period: 'day' | 'week' | 'month' = 'week') {
  return useQuery({
    queryKey: ['mttr', period],
    queryFn: () => analyticsApi.getMTTR(period),
    staleTime: 5 * 60 * 1000,
  });
}

export function useTeamPerformance() {
  return useQuery({
    queryKey: ['team-performance'],
    queryFn: () => analyticsApi.getTeamPerformance(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useServiceHealth() {
  return useQuery({
    queryKey: ['service-health'],
    queryFn: () => analyticsApi.getServiceHealth(),
    staleTime: 60 * 1000,
  });
}

export function useHeatmap() {
  return useQuery({
    queryKey: ['heatmap'],
    queryFn: () => analyticsApi.getHeatmap(),
    staleTime: 60 * 60 * 1000, // 1 hour
  });
}
