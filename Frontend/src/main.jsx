import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ThemeProvider from './components/ThemeProvider.jsx'
import { applyTheme, readTheme } from './lib/theme'
import AuthProvider from './components/AuthProvider.jsx'

applyTheme(readTheme())

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeProvider><AuthProvider><App /></AuthProvider></ThemeProvider>
  </StrictMode>,
)
