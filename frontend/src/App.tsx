// src/App.tsx
import { useEffect, useState } from 'react'
import './App.css'
import { useWebSocket } from './hooks/useWebSocket'
import { CommandPalette } from './components/CommandPalette'
import { TickerGrid } from './components/TickerGrid'

function App() {
  // This initializes the connection as soon as the app loads
  useWebSocket() 

  return (
    <div className="min-h-screen bg-background">
      <TickerGrid />
      <CommandPalette />
      {/* Other components... */}
    </div>
  )
}

function App() {
  const [backendMessage, setBackendMessage] = useState<string>('Loading...')

  useEffect(() => {
    // Test connection to your FastAPI backend
    fetch('http://localhost:8000/api/')
      .then(res => res.json())
      .then(data => setBackendMessage(data.message || 'Connected!'))
      .catch(err => setBackendMessage(`Error: ${err.message}`))
  }, [])

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center justify-center p-6">
      <h1 className="text-5xl font-bold mb-6 text-emerald-400">
        Bracket Bot Dashboard
      </h1>

      <p className="text-xl mb-8">
        Vite + React is running! Edit <code>src/App.tsx</code> and save to see magic ✨
      </p>

      <div className="bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-700 max-w-md w-full">
        <h2 className="text-2xl font-semibold mb-4">Backend Status</h2>
        <p className="text-lg">
          {backendMessage}
        </p>
      </div>

      <p className="mt-12 text-gray-400">
        Next: Add ticker cards, forms, and live WebSocket updates!
      </p>
    </div>
  )
}

export default App