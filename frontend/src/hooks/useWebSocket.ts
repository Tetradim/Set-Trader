import { useEffect, useRef } from 'react'
import { useStore } from '@/stores/useStore'
import { toast } from 'sonner'

export const useWebSocket = () => {
  const socket = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null)
  const { setTickers, setConnected, setPaused, setProfits } = useStore()

  const connect = () => {
    // 127.0.0.1 is more reliable than 'localhost' on Windows
    const WS_URL = 'ws://127.0.0.1:8000/ws'
    
    if (socket.current?.readyState === WebSocket.OPEN) return

    socket.current = new WebSocket(WS_URL)

    socket.current.onopen = () => {
      setConnected(true)
      toast.success('Connected to Bot Engine')
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
    }

    socket.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        
        if (data.type === 'INITIAL_STATE') {
          setTickers(data.tickers)
          setPaused(data.paused)
          // WE MUST SET PROFITS HERE OR THE CARDS WON'T SHOW DATA
          if (data.profits) setProfits(data.profits)
        } 
        
        if (data.type === 'TRADE_LOG') {
           useStore.getState().addLog(data.log)
        }
      } catch (err) {
        console.error("WS Message Error:", err)
      }
    }

    socket.current.onclose = () => {
      setConnected(false)
      // Attempt to reconnect every 3 seconds
      reconnectTimeout.current = setTimeout(connect, 3000)
    }

    socket.current.onerror = (err) => {
      console.error("WebSocket Error:", err)
      socket.current?.close()
    }
  }

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current)
      socket.current?.close()
    }
  }, [])

  const sendMessage = (action: string, payload: any = {}) => {
    if (socket.current?.readyState === WebSocket.OPEN) {
      const message = JSON.stringify({ action, ...payload })
      socket.current.send(message)
    } else {
      toast.error('Not connected to backend')
    }
  }

  return { sendMessage }
}