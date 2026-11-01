import { createContext, useContext, useEffect, useState } from 'react';

const Ctx = createContext<{ stage?: string; setStage: (s?: string) => void }>({ setStage: () => {} });

export function StageProvider({ children }: { children: React.ReactNode }) {
  const [stage, setStage] = useState<string | undefined>();
  return <Ctx.Provider value={{ stage, setStage }}>{children}</Ctx.Provider>;
}

export const useStage = () => useContext(Ctx).stage;

/** A page says where in the governed lifecycle it sits; the rail highlights that stage. */
export function useSetStage(stage?: string) {
  const { setStage } = useContext(Ctx);
  useEffect(() => { setStage(stage); return () => setStage(undefined); }, [stage, setStage]);
}
