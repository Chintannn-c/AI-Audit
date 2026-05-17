import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter } from 'react-router-dom'
import App from './App'
import { SessionProvider } from './context/SessionContext'
import { AuditProvider } from './context/AuditContext'
import './styles/theme.css'
import './styles/style.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <SessionProvider>
        <AuditProvider>
          <App />
        </AuditProvider>
      </SessionProvider>
    </HashRouter>
  </React.StrictMode>
)
