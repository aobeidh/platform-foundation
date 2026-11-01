import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useApi } from './provider';
import type { GovernedRecord, Operation, Transition } from './types';

export const keys = {
  me: ['me'] as const, kinds: ['kinds'] as const, plugins: ['plugins'] as const,
  records: (plural: string) => ['records', plural] as const,
  record: (plural: string, id: string) => ['records', plural, id] as const,
  versions: (plural: string, id: string) => ['versions', plural, id] as const,
  operations: ['operations'] as const, operation: (id: string) => ['operations', id] as const, activations: ['activations'] as const,
};

export function useMe() { const { api, identity } = useApi(); return useQuery({ queryKey: [...keys.me, identity.id], queryFn: api.me }); }
export function useKinds() { const { api } = useApi(); return useQuery({ queryKey: keys.kinds, queryFn: api.kinds, staleTime: 60_000 }); }
export function usePlugins() { const { api } = useApi(); return useQuery({ queryKey: keys.plugins, queryFn: api.plugins, staleTime: 60_000 }); }

/** True when the caller holds the capability. Drives what the portal offers; the API still checks. */
export function useCan() {
  const me = useMe();
  const caps = new Set(me.data?.capabilities.map((c) => c.name) ?? []);
  return (cap: string) => caps.has(cap);
}

export function useRecords<S>(plural: string, enabled = true) {
  const { api } = useApi();
  return useQuery({ queryKey: keys.records(plural), queryFn: () => api.list<S>(plural), enabled });
}
export function useRecord<S>(plural: string, id: string) {
  const { api } = useApi();
  return useQuery({ queryKey: keys.record(plural, id), queryFn: () => api.get<S>(plural, id) });
}
export function useVersions<S>(plural: string, id: string) {
  const { api } = useApi();
  return useQuery({ queryKey: keys.versions(plural, id), queryFn: () => api.versions<S>(plural, id) });
}

const running = (ops?: Operation[]) => !!ops?.some((o) => o.status === 'pending' || o.status === 'running');

export function useOperations() {
  const { api } = useApi();
  return useQuery({ queryKey: keys.operations, queryFn: api.operations, refetchInterval: (q) => (running(q.state.data?.items) ? 1000 : false) });
}
export function useOperation(id: string | null) {
  const { api } = useApi();
  return useQuery({ queryKey: keys.operation(id ?? ''), queryFn: () => api.operation(id!), enabled: !!id,
    refetchInterval: (q) => (q.state.data && running([q.state.data]) ? 800 : false) });
}
export function useActivations(enabled = true) { const { api } = useApi(); return useQuery({ queryKey: keys.activations, queryFn: api.activations, enabled }); }

function useInvalidate() {
  const qc = useQueryClient();
  return (plural: string, id?: string) => {
    void qc.invalidateQueries({ queryKey: keys.records(plural) });
    if (id) void qc.invalidateQueries({ queryKey: keys.versions(plural, id) });
    void qc.invalidateQueries({ queryKey: keys.activations });
  };
}

export function useTransition<S>(plural: string) {
  const { api } = useApi();
  const invalidate = useInvalidate();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; name: Transition['name']; revision: number; reason?: string }) => api.transition<S>(plural, v.id, v.name, v.revision, v.reason),
    onSuccess: (rec: GovernedRecord<S>) => { qc.setQueryData(keys.record(plural, rec.id), rec); invalidate(plural, rec.id); },
  });
}

export function useSaveDraft<S>(plural: string) {
  const { api } = useApi();
  const invalidate = useInvalidate();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id?: string; spec: S; revision?: number }) =>
      v.id ? api.updateDraft<S>(plural, v.id, v.spec, v.revision!) : api.create<S>(plural, v.spec),
    onSuccess: (rec: GovernedRecord<S>) => { qc.setQueryData(keys.record(plural, rec.id), rec); invalidate(plural, rec.id); },
  });
}

export function useSend() { const { api } = useApi(); return useMutation({ mutationFn: (v: { id: string; payload: Record<string, unknown> }) => api.send(v.id, v.payload) }); }
export function useSendBatch() {
  const { api } = useApi();
  const qc = useQueryClient();
  return useMutation({ mutationFn: (v: { id: string; payloads: Record<string, unknown>[] }) => api.sendBatch(v.id, v.payloads),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: keys.operations }); } });
}
export function useCancelOperation() {
  const { api } = useApi();
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: string) => api.cancelOperation(id), onSuccess: () => { void qc.invalidateQueries({ queryKey: keys.operations }); } });
}
