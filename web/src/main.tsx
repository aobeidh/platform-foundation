import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist';
import '@fontsource/ibm-plex-sans-arabic/arabic-400.css';
import '@fontsource/ibm-plex-sans-arabic/arabic-500.css';
import '@fontsource/ibm-plex-sans-arabic/arabic-600.css';
import './styles/globals.css';
import './i18n';
import { TooltipProvider } from '@/ui/atoms/tooltip';
import { ApiProvider } from '@/kit/api';
import { PrefsProvider, initialTheme } from '@/lib/prefs';
import { identities } from '@/data/seed';
import { App } from './app/App';
import { chooseTransport } from './app/wiring';

// Set the theme class before the first render, so there is no flash of the wrong theme.
document.documentElement.classList.toggle('dark', initialTheme() === 'dark');

void chooseTransport().then((transport) => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <PrefsProvider>
        <TooltipProvider delayDuration={250}>
          <ApiProvider transport={transport} identities={identities} initialIdentity="ada">
            <App />
          </ApiProvider>
        </TooltipProvider>
      </PrefsProvider>
    </StrictMode>,
  );
});
