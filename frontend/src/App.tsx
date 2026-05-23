import { useWebSocket } from './hooks/useWebSocket';
import { Dashboard } from './components/Dashboard';
import { AuthGate } from './components/AuthGate';
import { Toaster } from 'sonner';

function AuthedApp() {
  useWebSocket();

  return <Dashboard />;
}

function App() {

  return (
    <>
      <AuthGate>
        <AuthedApp />
      </AuthGate>
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: '#0a0608',
            border: '1px solid rgba(180,130,10,0.25)',
            color: '#f0e8d0',
            fontFamily: "'Rajdhani', system-ui, sans-serif",
            fontSize: '13px',
          },
        }}
      />
    </>
  );
}

export default App;
