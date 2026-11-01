import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Direction } from 'radix-ui';
import { useTranslation } from 'react-i18next';
import { setFormatLocale } from './format';

type Theme = 'light' | 'dark';
type Lang = 'en' | 'ar';

interface Prefs { theme: Theme; lang: Lang; dir: 'ltr' | 'rtl'; setTheme: (t: Theme) => void; toggleTheme: () => void; setLang: (l: Lang) => void; toggleLang: () => void }

const Ctx = createContext<Prefs | null>(null);

const store = {
  get: (k: string) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* unavailable */ } },
};

/** The theme set before first render (main.tsx) so there is no flash of the wrong theme. */
export function initialTheme(): Theme {
  const host = document.documentElement.getAttribute('data-theme');
  if (host === 'dark' || host === 'light') return host;
  const saved = store.get('pf-theme');
  if (saved === 'dark' || saved === 'light') return saved;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function PrefsProvider({ children }: { children: React.ReactNode }) {
  const { i18n } = useTranslation();
  const [theme, setThemeState] = useState<Theme>(() => (document.documentElement.classList.contains('dark') ? 'dark' : 'light'));
  const lang = (i18n.language === 'ar' ? 'ar' : 'en') as Lang;
  const dir = lang === 'ar' ? 'rtl' : 'ltr';

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    store.set('pf-theme', theme);
  }, [theme]);

  setFormatLocale(lang);
  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = dir;
    store.set('pf-lang', lang);
  }, [lang, dir]);

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
