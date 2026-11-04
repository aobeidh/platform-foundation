import { createContext, useContext, useMemo } from 'react';

/**
 * Where a portal is mounted. A page that owns the document leaves it unset: the theme class, `lang` and `dir` go
 * on <html>, overlays (dialogs, menus, tooltips) on <body>, and saved preferences under the kit's own keys. A portal
 * mounted inside a host's page, such as a custom element with a shadow root, sets `root` to its own element, so it
 * never changes the host's <html>; `overlays` to an element inside its styles' reach, where overlays open; and
 * `storagePrefix`, so the preferences it saves never mix with the host's (which may use this kit too).
 */
export interface Mount { root: HTMLElement; overlays?: HTMLElement; storagePrefix?: string }

const Ctx = createContext<Mount | null>(null);

export function MountProvider({ root, overlays, storagePrefix, children }: Mount & { children: React.ReactNode }) {
  const value = useMemo(() => ({ root, overlays, storagePrefix }), [root, overlays, storagePrefix]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** True inside a MountProvider: the portal is mounted in another page. */
export function useMounted(): boolean {
  return useContext(Ctx) !== null;
}

/** The element that carries the theme class, `lang` and `dir`: <html> unless a MountProvider names another. */
export function useMountRoot(): HTMLElement {
  return useContext(Ctx)?.root ?? document.documentElement;
}

/** Where overlays open: undefined (the document's <body>) unless a MountProvider names an element. */
export function useOverlayContainer(): HTMLElement | undefined {
  return useContext(Ctx)?.overlays;
}

/** The key a saved preference is kept under: `name`, after the mount's prefix when it has one. */
export function useStorageKey(name: string): string {
  return `${useContext(Ctx)?.storagePrefix ?? ''}${name}`;
}
