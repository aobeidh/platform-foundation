import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ApiClient } from './client';
import { DemoTokenSource, type DemoIdentity } from './identity';
import type { Transport } from './transport';
import type { SimulatedTransport } from './simulated/server';

interface ApiContextValue {
  api: ApiClient;
  transport: Transport;
  identity: DemoIdentity;
  identities: DemoIdentity[];
  setIdentity: (id: string) => void;
  simulated: SimulatedTransport | null;
}

const Ctx = createContext<ApiContextValue | null>(null);

function Bridge({ value, children }: { value: ApiContextValue; children: React.ReactNode }) {
  const qc = useQueryClient();
  // Background work in the simulated provider (operations advancing) refreshes what is on screen.
  useEffect(() => value.simulated?.subscribe(() => { void qc.invalidateQueries({ queryKey: ['operations'] }); }), [value.simulated, qc]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Wires one transport provider and one identity into every screen. Chosen once, in the app's wiring. */
export function ApiProvider({ transport, identities, initialIdentity, children }: {
  transport: Transport; identities: DemoIdentity[]; initialIdentity?: string; children: React.ReactNode;
}) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 2_000, retry: (n, e) => n < 1 && !(e && 'status' in e && (e as { status: number }).status < 500) } },
  }));
  const [identityId, setIdentityId] = useState(() => {
    try { return localStorage.getItem('pf-identity') ?? initialIdentity ?? identities[0].id; } catch { return initialIdentity ?? identities[0].id; }
  });
  const identity = identities.find((i) => i.id === identityId) ?? identities[0];
  const [tokens] = useState(() => new DemoTokenSource(identity));
  tokens.set(identity);
  const api = useMemo(() => new ApiClient(transport, tokens), [transport, tokens]);

  const value = useMemo<ApiContextValue>(() => ({
    api, transport, identity, identities,
    simulated: transport.kind === 'simulated' ? (transport as SimulatedTransport) : null,
    setIdentity: (id: string) => {
      try { localStorage.setItem('pf-identity', id); } catch { /* unavailable */ }
      setIdentityId(id);
      client.clear(); // nothing cached for one person may show for another
    },
  }), [api, transport, identity, identities, client]);

  return (
    <QueryClientProvider client={client}>
      <Bridge value={value}>{children}</Bridge>
    </QueryClientProvider>
  );
}

export function useApi() {
  const v = useContext(Ctx);
  if (!v) throw new Error('useApi needs ApiProvider');
  return v;
}
