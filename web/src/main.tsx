import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/geist';
import '@fontsource/ibm-plex-sans-arabic/arabic-400.css';
import '@fontsource/ibm-plex-sans-arabic/arabic-500.css';
import '@fontsource/ibm-plex-sans-arabic/arabic-600.css';
import './styles/globals.css';
import './i18n';
import { TooltipProvider } from '@/ui/atoms/tooltip';
import { ApiProvider, startSession } from '@/kit/api';
import { SignInProblem } from '@/kit/governed';
import { PrefsProvider, initialTheme } from '@/lib/prefs';
import { identities } from '@/data/seed';
import { App } from './app/App';
import { chooseTransport } from './app/wiring';

// Set the theme class before the first render, so there is no flash of the wrong theme.
document.documentElement.classList.toggle('dark', initialTheme() === 'dark');

// The transport, then how people sign in (OIDC or demo identities), both chosen once before the first render.
void chooseTransport().then(async (transport) => {
  const session = await startSession(transport);
  const body = session.kind === 'oidc' ? (
    <ApiProvider transport={transport} tokens={session.tokens} account={session.tokens.account} onSignOut={() => session.tokens.signOut()}>
      <App />
    </ApiProvider>
  ) : session.kind === 'demo' ? (
    <ApiProvider transport={transport} identities={identities} initialIdentity="ada"><App /></ApiProvider>
  ) : <SignInProblem reason={session.kind === 'failed' ? session.reason : null} onRetry={() => location.reload()} />;
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <PrefsProvider>
        <TooltipProvider delayDuration={250}>{body}</TooltipProvider>
      </PrefsProvider>
    </StrictMode>,
  );
});
