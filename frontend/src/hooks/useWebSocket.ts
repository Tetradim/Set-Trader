import { useEffect, useRef } from 'react'
import { useStore } from '@/stores/useStore'
import { toast } from 'sonner'

export const useWebSocket = () => {
  const socket = useRef<WebSocket | null>(null)
  const { setTickers, setConnected, setPaused } = useStore()

  useEffect(() => {
    // Replace with your actual backend URL
    const WS_URL = 'ws://localhost:8000/ws'
    socket.current = new WebSocket(WS_URL)

    socket.current.onopen = () => {
      setConnected(true)
      toast.success('Connected to Bot Engine')
    }

    socket.current.onmessage = (event) => {
      const data = JSON.parse(event.data)
      
      // Handle different message types from your backend
      if (data.type === 'INITIAL_STATE') {
        setTickers(data.tickers)
        setPaused(data.paused)
      } else if (data.type === 'TICKER_UPDATE') {
        // This keeps the UI snappy by only updating what changed
        useStore.getState().updateTicker(data.symbol, data.update)
      }
    }

    socket.current.onclose = () => {
      setConnected(false)
      toast.error('Bot Connection Lost')
    }

    return () => socket.current?.close()
  }, [])

  const sendMessage = (action: string, payload: any = {}) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      socket.current.send(JSON.stringify({ action, ...payload }))
    }
  }

  return { sendMessage }
}