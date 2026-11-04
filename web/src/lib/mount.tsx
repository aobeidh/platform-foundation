import { createContext, useContext } from 'react';

/**
 * Where a portal is mounted. A page that owns the document leaves both unset: the theme class, `lang` and `dir` go
 * on <html> and overlays (dialogs, menus, tooltips) on <body>. A portal mounted inside a host's page, such as a
 * custom element with a shadow root, sets `root` to its own element, so it never changes the host's <html>, and
 * `overlays` to an element inside its styles' reach, where overlays open.
 */
export interface Mount { root: HTMLElement; overlays?: HTMLElement }

const Ctx = createContext<Mount | null>(null);

export function MountProvider({ root, overlays, children }: Mount & { children: React.ReactNode }) {
  return <Ctx.Provider value={{ root, overlays }}>{children}</Ctx.Provider>;
}

/** The element that carries the theme class, `lang` and `dir`: <html> unless a MountProvider names another. */
export function useMountRoot(): HTMLElement {
  return useContext(Ctx)?.root ?? document.documentElement;
}

/** Where overlays open: undefined (the document's <body>) unless a MountProvider names an element. */
export function useOverlayContainer(): HTMLElement | undefined {
  return useContext(Ctx)?.overlays;
}
