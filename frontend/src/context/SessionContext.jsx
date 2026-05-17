import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'

const SessionContext = createContext(null)

// Keep a reference to the native fetch before we wrap it
const nativeFetch = window.fetch.bind(window)

export function SessionProvider({ children }) {
  const [sessionId, setSessionId] = useState(() => {
    return localStorage.getItem('stataudit_session_id') || ''
  })
  const secretRef = useRef(localStorage.getItem('stataudit_session_secret'))
  const handshakePromiseRef = useRef(null)

  const initSession = useCallback(async () => {
    if (handshakePromiseRef.current) {
      return handshakePromiseRef.current
    }

    const promise = (async () => {
      try {
        const res = await nativeFetch('/api/session/create', {
          method: 'POST',
          credentials: 'include'
        })
        if (res.ok) {
          const data = await res.json()
          localStorage.setItem('stataudit_session_secret', data.session_secret)
          secretRef.current = data.session_secret
          console.log('[SECURITY] Handshake successful, session active.')
        } else {
          console.error('[SECURITY] Handshake failed:', res.statusText)
        }
      } catch (err) {
        console.error('[SECURITY] Handshake exception:', err)
      } finally {
        handshakePromiseRef.current = null
      }
    })()

    handshakePromiseRef.current = promise
    return promise
  }, [])

  // Generate or retrieve session ID
  useEffect(() => {
    if (!sessionId) {
      const newId = 'sess_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now()
      localStorage.setItem('stataudit_session_id', newId)
      setSessionId(newId)
    }
  }, [sessionId])

  // Init session on mount
  useEffect(() => {
    if (!secretRef.current) {
      initSession()
    }
  }, [initSession])

  const secureFetch = useCallback(async (url, options = {}) => {
    options.headers = options.headers || {}

    let secret = secretRef.current || localStorage.getItem('stataudit_session_secret')

    if (!secret && !url.includes('/api/session/create')) {
      await initSession()
      secret = secretRef.current
    }

    if (secret) {
      if (options.headers instanceof Headers) {
        options.headers.set('Authorization', `Bearer ${secret}`)
      } else {
        options.headers['Authorization'] = `Bearer ${secret}`
      }
    }

    options.credentials = 'include'

    try {
      const response = await nativeFetch(url, options)

      // Handle secret rotation
      const rotatedSecret = response.headers.get('X-Session-Secret')
      if (rotatedSecret) {
        console.log('[SECURITY] Rotating session secret')
        localStorage.setItem('stataudit_session_secret', rotatedSecret)
        secretRef.current = rotatedSecret
      }

      // Handle unauthorized
      if (response.status === 401 && !url.includes('/api/session/create')) {
        console.warn('[SECURITY] Session expired. Re-authenticating...')
        localStorage.removeItem('stataudit_session_secret')
        secretRef.current = null
        window.location.reload()
      }

      return response
    } catch (err) {
      console.error('[SECURITY] Fetch error:', err)
      throw err
    }
  }, [initSession])

  const clearSession = useCallback(async () => {
    try {
      await secureFetch('/api/session/revoke', { method: 'POST' })
    } catch (e) {
      console.error('Revocation failed', e)
    }
    localStorage.removeItem('stataudit_session_secret')
    localStorage.removeItem('stataudit_session_id')
    secretRef.current = null
    window.location.reload()
  }, [secureFetch])

  return (
    <SessionContext.Provider value={{ sessionId, secureFetch, clearSession }}>
      {children}
    </SessionContext.Provider>
  )
}

export function useSession() {
  const ctx = useContext(SessionContext)
  if (!ctx) throw new Error('useSession must be used within SessionProvider')
  return ctx
}
