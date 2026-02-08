import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { incidentApi } from '@/lib/api';
import { Incident, IncidentFilter } from '@/types/incident';
import { toast } from 'sonner';

export function useIncidents(filters?: IncidentFilter, page = 1, limit = 20) {
  return useQuery({
    queryKey: ['incidents', filters, page, limit],
    queryFn: () => incidentApi.list(filters, page, limit),
    refetchInterval: 30000, // Refetch every 30 seconds
  });
}

export function useIncident(id: string) {
  return useQuery({
    queryKey: ['incident', id],
    queryFn: () => incidentApi.get(id),
    enabled: !!id,
  });
}

export function useIncidentContext(id: string) {
  return useQuery({
    queryKey: ['incident-context', id],
    queryFn: () => incidentApi.getContext(id),
    enabled: !!id,
  });
}

export function useIncidentTimeline(id: string) {
  return useQuery({
    queryKey: ['incident-timeline', id],
    queryFn: () => incidentApi.getTimeline(id),
    enabled: !!id,
  });
}

export function useIncidentStats() {
  return useQuery({
    queryKey: ['incident-stats'],
    queryFn: () => incidentApi.getStats(),
    refetchInterval: 60000, // Refetch every minute
  });
}

export function useSimilarIncidents(id: string) {
  return useQuery({
    queryKey: ['similar-incidents', id],
    queryFn: () => incidentApi.getSimilar(id),
    enabled: !!id,
  });
}

export function useAcknowledgeIncident() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: (id: string) => incidentApi.acknowledge(id),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['incident', incident.id] });
      queryClient.invalidateQueries({ queryKey: ['incident-stats'] });
      toast.success('Incident acknowledged');
    },
    onError: () => {
      toast.error('Failed to acknowledge incident');
    },
  });
}

export function useResolveIncident() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, resolution }: { id: string; resolution?: string }) =>
      incidentApi.resolve(id, resolution),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['incident', incident.id] });
      queryClient.invalidateQueries({ queryKey: ['incident-stats'] });
      toast.success('Incident resolved');
    },
    onError: () => {
      toast.error('Failed to resolve incident');
    },
  });
}

export function useEscalateIncident() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, to }: { id: string; to?: string }) =>
      incidentApi.escalate(id, to),
    onSuccess: (incident) => {
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: ['incident', incident.id] });
      toast.success('Incident escalated');
    },
    onError: () => {
      toast.error('Failed to escalate incident');
    },
  });
}

export function useAddNote() {
  const queryClient = useQueryClient();
  
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      incidentApi.addNote(id, note),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: ['incident-timeline', variables.id] });
      toast.success('Note added');
    },
    onError: () => {
      toast.error('Failed to add note');
    },
  });
}
