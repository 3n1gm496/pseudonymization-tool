import { memo, useEffect, useRef, useState, type JSX } from 'react'
import axios, { setCsrfToken } from './utils/axios'
import Header from './components/Header'
import Scanner from './components/Scanner'
import FindingsTable from './components/FindingsTable'
import Results from './components/Results'
import RevertPanel from './components/RevertPanel'
import SettingsPanel from './components/SettingsPanel'
import { useToast } from './hooks/useToast'
import LoginForm from './components/LoginForm'
import type { Batch, CurrentUser, UserRole } from './types'

type ToolMode = 'pseudonymize' | 'revert'
type CurrentStep = 'scanner' | 'findings' | 'results'

interface AuthMeResponse {
  username: string
  role?: UserRole
  default_password?: boolean
}

interface LoginResponse {
  username: string
  role?: UserRole
  default_password?: boolean
}

interface ApplyTextResponse {
  pseudonymized_text?: string
}

interface ApplyHandlerArgs {
  batchId: string
  fileId?: string
  isTextInput: boolean
  sourceText?: string
}

// Memoize heavy components to prevent unnecessary re-renders
const MemoizedScanner = memo(Scanner)
const MemoizedFindingsTable = memo(FindingsTable)
const MemoizedResults = memo(Results)
const MemoizedRevertPanel = memo(RevertPanel)
const MemoizedSettingsPanel = memo(SettingsPanel)

const App = (): JSX.Element => {
  const [currentStep, setCurrentStep] = useState<CurrentStep>('scanner')
  const [toolMode, setToolMode] = useState<ToolMode>('pseudonymize')
  const [batch, setBatch] = useState<Batch | null>(null)
  const [pseudonymizedText, setPseudonymizedText] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [defaultPasswordWarning, setDefaultPasswordWarning] = useState(false)
  const { showToast, ToastContainer } = useToast()

  // Ref to cancel ongoing SSE/polling when user resets/logs out
  const pollingCancelledRef = useRef(false)
  const sseAbortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const bootstrapAuth = async (): Promise<void> => {
      try {
        const response = await axios.get<AuthMeResponse>('/api/auth/me')
        setCurrentUser({
          username: response.data.username,
          role: response.data.role ?? 'operator',
        })
        if (response.data.default_password) {
          setDefaultPasswordWarning(true)
        }
        // Fetch role from /api/users/me if not returned by /api/auth/me
        if (!response.data.role) {
          try {
            const meRes = await axios.get<CurrentUser>('/api/users/me')
            setCurrentUser({ username: meRes.data.username, role: meRes.data.role })
          } catch {
            // ignore — role defaults to 'operator' (safe default)
          }
        }
      } catch {
        setCurrentUser(null)
      } finally {
        setAuthLoading(false)
      }
    }
    void bootstrapAuth()
  }, [])

  /**
   * Attende il completamento del batch tramite SSE.
   * Fallback automatico al polling se SSE non è supportato o fallisce.
   */
  const waitForBatchCompletion = async (
    batchId: string,
    timeoutMs = 25 * 60 * 1000,
    pollIntervalMs = 1500,
  ): Promise<Batch> => {
    pollingCancelledRef.current = false

    // Tenta SSE prima
    if (typeof EventSource !== 'undefined') {
      try {
        const result = await new Promise<Batch>((resolve, reject) => {
          const abortCtrl = new AbortController()
          sseAbortRef.current = abortCtrl
          const timeoutId = setTimeout(() => {
            abortCtrl.abort()
            reject(new Error('Timeout SSE attesa completamento batch'))
          }, timeoutMs)

          const es = new EventSource(`/api/batches/${batchId}/events`)

          es.onmessage = (event: MessageEvent<string>) => {
            if (pollingCancelledRef.current) {
              clearTimeout(timeoutId)
              es.close()
              reject(new Error("SSE cancellato dall'utente"))
              return
            }
            try {
              const data = JSON.parse(event.data) as {
                type: string
                status?: string
                error_message?: string
                message?: string
              }
              if (data.type === 'status') {
                const status = (data.status ?? '').toLowerCase()
                if (status === 'done' || status === 'done_with_errors') {
                  clearTimeout(timeoutId)
                  es.close()
                  // Fetch batch completo con findings
                  axios
                    .get<Batch>(`/api/batches/${batchId}`)
                    .then((r) => resolve(r.data))
                    .catch(reject)
                } else if (status === 'error') {
                  clearTimeout(timeoutId)
                  es.close()
                  reject(new Error(data.error_message ?? 'Errore durante apply del batch'))
                }
              } else if (data.type === 'timeout') {
                clearTimeout(timeoutId)
                es.close()
                reject(new Error('Timeout SSE lato server'))
              } else if (data.type === 'error') {
                clearTimeout(timeoutId)
                es.close()
                reject(new Error(data.message ?? 'Errore SSE'))
              }
            } catch {
              // JSON parse error — ignora
            }
          }

          es.onerror = () => {
            clearTimeout(timeoutId)
            es.close()
            // Fallback al polling
            reject(new Error('SSE_FALLBACK'))
          }
        })
        sseAbortRef.current = null
        return result
      } catch (err: unknown) {
        sseAbortRef.current = null
        const msg = err instanceof Error ? err.message : ''
        if (msg !== 'SSE_FALLBACK') {
          throw err
        }
        // Continua con il polling come fallback
      }
    }

    // Fallback: polling classico
    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      if (pollingCancelledRef.current) {
        throw new Error("Polling cancellato dall'utente")
      }
      const statusResponse = await axios.get<Batch>(`/api/batches/${batchId}/status`)
      const currentBatch = statusResponse.data
      const status = String(currentBatch?.status ?? '').toLowerCase()
      if (status === 'done' || status === 'done_with_errors') {
        const fullBatchResponse = await axios.get<Batch>(`/api/batches/${batchId}`)
        return fullBatchResponse.data
      }
      if (status === 'error') {
        const batchWithError = currentBatch as Batch & { error_message?: string }
        throw new Error(batchWithError.error_message ?? 'Errore durante apply del batch')
      }
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(resolve, pollIntervalMs)
        const cancelCheck = setInterval(() => {
          if (pollingCancelledRef.current) {
            clearTimeout(timer)
            clearInterval(cancelCheck)
            reject(new Error("Polling cancellato dall'utente"))
          }
        }, 100)
        setTimeout(() => clearInterval(cancelCheck), pollIntervalMs)
      })
    }
    throw new Error('Timeout attesa completamento apply batch')
  }

  const handleLogin = async (username: string, password: string): Promise<void> => {
    setIsLoading(true)
    try {
      const response = await axios.post<LoginResponse>('/api/auth/login', { username, password })
      const csrfTokenFromResponse = response.headers['x-csrf-token'] as string | undefined
      if (csrfTokenFromResponse) {
        setCsrfToken(csrfTokenFromResponse)
      }
      if (response.data.default_password) {
        setDefaultPasswordWarning(true)
      }
      // Fetch full user info (including role) from /api/users/me
      try {
        const meRes = await axios.get<CurrentUser>('/api/users/me')
        setCurrentUser({ username: meRes.data.username, role: meRes.data.role })
      } catch {
        // Fallback: use data from login response
        setCurrentUser({
          username: response.data.username,
          role: response.data.role ?? 'operator',
        })
      }
      showToast('Login effettuato', 'success')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      showToast(axiosError.response?.data?.detail ?? 'Login fallito', 'error')
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const handleLogout = async (): Promise<void> => {
    pollingCancelledRef.current = true
    sseAbortRef.current?.abort()
    sseAbortRef.current = null
    try {
      await axios.post('/api/auth/logout')
    } catch {
      // ignore
    }
    setCurrentUser(null)
    setBatch(null)
    setPseudonymizedText(null)
    setCurrentStep('scanner')
    showToast('Logout effettuato', 'info')
  }

  const handleScan = (scanResult: Batch): void => {
    setBatch(scanResult)
    setCurrentStep('findings')
  }

  const handleApply = async ({
    batchId,
    fileId,
    isTextInput,
    sourceText,
  }: ApplyHandlerArgs): Promise<void> => {
    setIsLoading(true)
    try {
      if (isTextInput) {
        const response = await axios.post<ApplyTextResponse>('/api/console/apply', {
          batch_id: batchId,
          file_id: fileId,
          text: sourceText ?? '',
        })
        setPseudonymizedText(response.data.pseudonymized_text ?? '')
      } else {
        const applyResponse = await axios.post<Batch>(`/api/batches/${batchId}/apply`)
        if (applyResponse.status === 202) {
          showToast('Apply accodato, attendo completamento...', 'info')
          const completedBatch = await waitForBatchCompletion(batchId)
          setBatch((prev) => ({
            ...completedBatch,
            passphrase: (prev as (Batch & { passphrase?: string }) | null)?.passphrase,
            is_text_input: false,
          }) as Batch)
        }
        setPseudonymizedText('')
      }
      setCurrentStep('results')
      showToast('Pseudonimizzazione completata', 'success')
    } catch (error: unknown) {
      const err = error as { message?: string; response?: { data?: { detail?: string } } }
      if (err.message === "Polling cancellato dall'utente") {
        return
      }
      showToast(
        err.response?.data?.detail ?? err.message ?? "Errore durante l'applicazione",
        'error',
      )
    } finally {
      setIsLoading(false)
    }
  }

  const handleReset = (): void => {
    pollingCancelledRef.current = true
    sseAbortRef.current?.abort()
    sseAbortRef.current = null
    setBatch(null)
    setPseudonymizedText(null)
    setCurrentStep('scanner')
  }

  const handleSwitchMode = (mode: ToolMode): void => {
    setToolMode(mode)
    if (mode === 'pseudonymize') {
      handleReset()
    }
  }

  if (authLoading) {
    return <div className="min-h-screen bg-slate-50 dark:bg-slate-950" />
  }

  if (!currentUser) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        <Header user={null} onLogout={null} onSettingsClick={() => setIsSettingsOpen(true)} />
        <main className="max-w-7xl mx-auto py-8 px-4">
          <LoginForm onLogin={handleLogin} isLoading={isLoading} />
        </main>
        <MemoizedSettingsPanel
          isOpen={isSettingsOpen}
          onClose={() => setIsSettingsOpen(false)}
          showToast={showToast}
        />
        <ToastContainer />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Header
        user={currentUser.username}
        userRole={currentUser.role}
        onLogout={() => void handleLogout()}
        onSettingsClick={() => setIsSettingsOpen(true)}
      />
      {/* Default password warning banner */}
      {defaultPasswordWarning && (
        <div
          role="alert"
          className="bg-amber-50 dark:bg-amber-900/30 border-b border-amber-300 dark:border-amber-700"
        >
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-amber-600 dark:text-amber-400 text-xl" aria-hidden="true">
                &#9888;
              </span>
              <p className="text-sm text-amber-800 dark:text-amber-200">
                <strong>Attenzione:</strong> stai usando la password predefinita. Cambiala subito
                nelle{' '}
                <button
                  onClick={() => {
                    setIsSettingsOpen(true)
                    setDefaultPasswordWarning(false)
                  }}
                  className="underline font-semibold hover:text-amber-900 dark:hover:text-amber-100 focus:outline-none focus:ring-2 focus:ring-amber-500 rounded"
                >
                  Impostazioni
                </button>{' '}
                per proteggere il sistema.
              </p>
            </div>
            <button
              onClick={() => setDefaultPasswordWarning(false)}
              aria-label="Chiudi avviso password predefinita"
              className="text-amber-600 dark:text-amber-400 hover:text-amber-900 dark:hover:text-amber-100 focus:outline-none focus:ring-2 focus:ring-amber-500 rounded p-1 flex-shrink-0"
            >
              &#x2715;
            </button>
          </div>
        </div>
      )}
      <main className="max-w-7xl mx-auto py-8 px-4 space-y-8">
        <div className="flex gap-3 justify-center">
          <button
            onClick={() => handleSwitchMode('pseudonymize')}
            className={`px-4 py-2 rounded-lg font-medium ${
              toolMode === 'pseudonymize' ? 'bg-blue-600 text-white' : 'bg-slate-200 dark:bg-slate-700'
            }`}
          >
            Pseudonimizza
          </button>
          <button
            onClick={() => handleSwitchMode('revert')}
            className={`px-4 py-2 rounded-lg font-medium ${
              toolMode === 'revert' ? 'bg-blue-600 text-white' : 'bg-slate-200 dark:bg-slate-700'
            }`}
          >
            Revert
          </button>
        </div>
        {toolMode === 'revert' && (
          <MemoizedRevertPanel
            batch={batch}
            pseudonymizedText={pseudonymizedText}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
            showToast={showToast}
          />
        )}
        {toolMode === 'pseudonymize' && (
          <>
            {/* Progress Bar */}
            <div
              className="flex items-center gap-3 justify-center mb-8"
              aria-label="Stato avanzamento"
            >
              <div
                className={`px-4 py-2 rounded-lg font-medium ${
                  currentStep === 'scanner' ? 'bg-blue-600 text-white' : 'bg-green-600 text-white'
                }`}
              >
                {currentStep === 'scanner' ? '1' : '✓'} Scansione
              </div>
              <div className="h-1 flex-1 max-w-16 bg-slate-300 dark:bg-slate-700"></div>
              <div
                className={`px-4 py-2 rounded-lg font-medium ${
                  currentStep === 'findings'
                    ? 'bg-blue-600 text-white'
                    : currentStep === 'results'
                      ? 'bg-green-600 text-white'
                      : 'bg-slate-300 dark:bg-slate-700'
                }`}
              >
                {currentStep === 'results' ? '✓' : '2'} Revisione
              </div>
              <div className="h-1 flex-1 max-w-16 bg-slate-300 dark:bg-slate-700"></div>
              <div
                className={`px-4 py-2 rounded-lg font-medium ${
                  currentStep === 'results' ? 'bg-blue-600 text-white' : 'bg-slate-300 dark:bg-slate-700'
                }`}
              >
                3 Risultato
              </div>
            </div>
            {/* Scanner Step */}
            {currentStep === 'scanner' && (
              <MemoizedScanner onScan={handleScan} isLoading={isLoading} />
            )}
            {/* Findings Review Step */}
            {currentStep === 'findings' && batch && (
              <MemoizedFindingsTable
                batch={batch}
                onApply={handleApply}
                isLoading={isLoading}
              />
            )}
            {/* Results Step */}
            {currentStep === 'results' && batch && (
              <MemoizedResults
                batch={batch}
                pseudonymizedText={pseudonymizedText}
                onNewScan={handleReset}
              />
            )}
          </>
        )}
      </main>
      <MemoizedSettingsPanel
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        showToast={showToast}
        currentUsername={currentUser.username}
        currentRole={currentUser.role}
      />
      <ToastContainer />
    </div>
  )
}

export default App
