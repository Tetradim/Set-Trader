import { useState, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useStore } from './stores/useStore';
import { Dashboard } from './components/Dashboard';
import { BetaRegistrationModal } from './components/BetaRegistrationModal';
import { Toaster } from 'sonner';
import { apiFetch } from './lib/api';

function App() {
  useWebSocket();
  const [betaChecked, setBetaChecked] = useState(false);
  const [betaRegistered, setBetaRegistered] = useState(false);

  useEffect(() => {
    apiFetch('/api/beta/status')
      .then((data) => {
        setBetaRegistered(!!data.registered);
        setBetaChecked(true);
      })
      .catch(() => {
        setBetaChecked(true);
      });
  }, []);

  if (!betaChecked) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background" data-testid="beta-loading">
        <div className="text-muted-foreground text-sm animate-pulse">Initializing Sentinel Pulse...</div>
      </div>
    );
  }

  return (
    <>
      {!betaRegistered && (
        <BetaRegistrationModal onRegistered={() => setBetaRegistered(true)} />
      )}
      {betaRegistered && <Dashboard />}
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: 'hsl(220 40% 8%)',
            border: '1px solid hsl(215 20% 16%)',
            color: 'hsl(213 31% 91%)',
            fontFamily: 'IBM Plex Sans, system-ui, sans-serif',
          },
        }}
      />
    </>
  );
}

export default App;
