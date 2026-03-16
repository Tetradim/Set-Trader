import { useWebSocket } from './hooks/useWebSocket';
import { useStore } from './stores/useStore';
import { Dashboard } from './components/Dashboard';
import { Toaster } from 'sonner';

function App() {
  useWebSocket();
  return (
    <>
      <Dashboard />
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
