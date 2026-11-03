import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { QueryClient, QueryClientProvider, useQueryClient } from '@tanstack/react-query';
import { ApiClient } from './client';
import { DemoTokenSource, type Account, type DemoIdentity, type TokenSource } from './identity';
import type { Transport } from './transport';
import type { SimulatedTransport } from './simulated/server';

interface ApiContextValue {
  api: ApiClient;
  transport: Transport;
  /** The demo identity in use, or null when people sign in through an identity provider. */
  identity: DemoIdentity | null;
  identities: DemoIdentity[];
  setIdentity: (id: string) => void;
  /** The person signed in through an identity provider, or null with demo identities. */
  account: Account | null;
  signOut: (() => void) | null;
  simulated: SimulatedTransport | null;
}

const Ctx = createContext<ApiContextValue | null>(null);

function Bridge({ value, children }: { value: ApiContextValue; children: React.ReactNode }) {
  const qc = useQueryClient();
  // Background work in the simulated provider (operations advancing) refreshes what is on screen.
  useEffect(() => value.simulated?.subscribe(() => { void qc.invalidateQueries({ queryKey: ['operations'] }); }), [value.simulated, qc]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/**
 * Wires one transport provider and one identity into every screen. Chosen once, in the app's wiring: demo
 * identities (`identities`), or a signed-in person (`tokens` with their `account`, from startSession).
 */
export function ApiProvider({ transport, identities = [], initialIdentity, tokens: signedIn, account = null, onSignOut, children }: {
  transport: Transport; identities?: DemoIdentity[]; initialIdentity?: string;
  tokens?: TokenSource; account?: Account | null; onSignOut?: () => void; children: React.ReactNode;
}) {
  const [client] = useState(() => new QueryClient({
    defaultOptions: { queries: { staleTime: 2_000, retry: (n, e) => n < 1 && !(e && 'status' in e && (e as { status: number }).status < 500) } },
  }));
  const [identityId, setIdentityId] = useState(() => {
    try { return localStorage.getItem('pf-identity') ?? initialIdentity ?? identities[0]?.id; } catch { return initialIdentity ?? identities[0]?.id; }
  });
  const identity = signedIn ? null : identities.find((i) => i.id === identityId) ?? identities[0] ?? null;
  const [demo] = useState(() => (identity ? new DemoTokenSource(identity) : null));
  if (demo && identity) demo.set(identity);
  const [none] = useState<TokenSource>(() => ({ token: () => null }));
  const tokens: TokenSource = signedIn ?? demo ?? none;
  const api = useMemo(() => new ApiClient(transport, tokens), [transport, tokens]);

  const value = useMemo<ApiContextValue>(() => ({
    api, transport, identity, identities: signedIn ? [] : identities, account: signedIn ? account : null,
    signOut: signedIn && onSignOut ? () => { client.clear(); onSignOut(); } : null,
    simulated: transport.kind === 'simulated' ? (transport as SimulatedTransport) : null,
    setIdentity: (id: string) => {
      if (signedIn) return;
      try { localStorage.setItem('pf-identity', id); } catch { /* unavailable */ }
      setIdentityId(id);
      client.clear(); // nothing cached for one person may show for another
    },
  }), [api, transport, identity, identities, signedIn, account, onSignOut, client]);

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
