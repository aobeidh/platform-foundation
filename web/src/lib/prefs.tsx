import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Direction } from 'radix-ui';
import { useTranslation } from 'react-i18next';
import { setFormatLocale } from './format';
import { useMountRoot, useStorageKey } from './mount';

type Theme = 'light' | 'dark';
type Lang = 'en' | 'ar';

interface Prefs { theme: Theme; lang: Lang; dir: 'ltr' | 'rtl'; setTheme: (t: Theme) => void; toggleTheme: () => void; setLang: (l: Lang) => void; toggleLang: () => void }

const Ctx = createContext<Prefs | null>(null);

const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* unavailable */ } },
};

/** The theme set before first render (main.tsx) so there is no flash of the wrong theme. A mounted portal passes
 * its own root, whose `data-theme` the host may set, and its storage prefix. */
export function initialTheme(root: HTMLElement = document.documentElement, storagePrefix = ''): Theme {
  const host = root.getAttribute('data-theme');
  if (host === 'dark' || host === 'light') return host;
  const saved = store.get(`${storagePrefix}pf-theme`);
  if (saved === 'dark' || saved === 'light') return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const { i18n } = useTranslation();
  const root = useMountRoot();
  const themeKey = useStorageKey('pf-theme');
  const langKey = useStorageKey('pf-lang');
  const [theme, setThemeState] = useState<Theme>(() => (root.classList.contains('dark') ? 'dark' : 'light'));

  // A host that mounts the portal may set the theme on the root's data-theme later; the preference follows it.
  useEffect(() => {
    const follow = () => {
      const asked = root.getAttribute('data-theme');
      if (asked === 'dark' || asked === 'light') setThemeState(asked);
    };
    const mo = new MutationObserver(follow);
    mo.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
    return () => mo.disconnect();
  }, [root]);
  const lang = (i18n.language === 'ar' ? 'ar' : 'en') as Lang;
  const dir = lang === 'ar' ? 'rtl' : 'ltr';

  useEffect(() => {
    root.classList.toggle('dark', theme === 'dark');
    store.set(themeKey, theme);
  }, [root, theme, themeKey]);

  setFormatLocale(lang);
  useEffect(() => {
    root.lang = lang;
    root.dir = dir;
    store.set(langKey, lang);
  }, [root, lang, dir, langKey]);

  const setLang = useCallback((l: Lang) => { void i18n.changeLanguage(l); }, [i18n]);
  const value = useMemo<Prefs>(() => ({
    theme, lang, dir, setTheme: setThemeState, toggleTheme: () => setThemeState((t) => (t === 'dark' ? 'light' : 'dark')),
    setLang, toggleLang: () => setLang(lang === 'ar' ? 'en' : 'ar'),
  }), [theme, lang, dir, setLang]);

  return (
    <Ctx.Provider value={value}>
      <Direction.Provider dir={dir}>{children}</Direction.Provider>
    </Ctx.Provider>
  );
}

export function usePrefs() {
  const v = useContext(Ctx);
  if (!v) throw new Error('usePrefs needs PrefsProvider');
  return v;
}
