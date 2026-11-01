import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { ar, en } from './strings';

const saved = (() => { try { return localStorage.getItem('pf-lang'); } catch { return null; } })();

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: saved === 'ar' ? 'ar' : 'en',
  fallbackLng: 'en',
  keySeparator: false,
  nsSeparator: false,
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;
