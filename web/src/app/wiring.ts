import { HttpTransport, serviceIsReachable, SimulatedTransport, type Transport } from '@/kit/api';
import { seed } from '@/data/seed';

// The composition root of the portal: the only place a provider is chosen (P3, F6).
// simulated: the in-browser provider (published demo, `build:single`).
// http: a real service on this origin (`npm run dev` proxies /api to API_URL).
// auto: http when a service answers /health/live, otherwise simulated.
export async function chooseTransport(): Promise<Transport> {
  const forced = new URLSearchParams(location.search).get('api');
  const mode = forced === 'simulated' || forced === 'http' ? forced : __API_MODE__;
  if (mode === 'http' || (mode === 'auto' && (await serviceIsReachable()))) return new HttpTransport();
  return new SimulatedTransport(seed);
}
