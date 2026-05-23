import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { installUiLogging, uiLog } from './lib/clientLogger'

installUiLogging()
uiLog.event('ui.react_mount', { message: 'React root mounting' })

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
