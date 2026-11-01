import { useSearchParams } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/ui/atoms/tabs';
import { CountBadge } from '@/ui/atoms/misc';

export interface TabDef { id: string; label: React.ReactNode; count?: number; content: React.ReactNode }

/** Underlined tabs; each carries its content, and the active tab lives in the address (?tab=). */
export function TabBar({ tabs, param = 'tab' }: { tabs: TabDef[]; param?: string }) {
  const [params, setParams] = useSearchParams();
  const active = tabs.find((t) => t.id === params.get(param))?.id ?? tabs[0].id;
  return (
    <Tabs value={active} onValueChange={(v) => setParams((p) => { const n = new URLSearchParams(p); n.set(param, v); return n; }, { replace: true })}>
      <TabsList variant="line" className="w-full justify-start">
        {tabs.map((t) => (
          <TabsTrigger key={t.id} value={t.id}>{t.label}{t.count !== undefined && <CountBadge count={t.count} />}</TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((t) => <TabsContent key={t.id} value={t.id} className="pt-4">{t.content}</TabsContent>)}
    </Tabs>
  );
}
