import { memo, useEffect, useRef, useState } from 'react'
import axios, { setCsrfToken } from './utils/axios'
import Header from './components/Header'
import Scanner from './components/Scanner'
import FindingsTable from './components/FindingsTable'
import Results from './components/Results'
import RevertPanel from './components/RevertPanel'
import SettingsPanel from './components/SettingsPanel'
import { useToast } from './hooks/useToast'
import LoginForm from './components/LoginForm'
// Memoize heavy components to prevent unnecessary re-renders
const MemoizedScanner = memo(Scanner)
const MemoizedFindingsTable = memo(FindingsTable)
const MemoizedResults = memo(Results)
const MemoizedRevertPanel = memo(RevertPanel)
const MemoizedSettingsPanel = memo(SettingsPanel)

const App = () => {
  const [currentStep, setCurrentStep] = useState('scanner') // scanner | findings | results
  const [toolMode, setToolMode] = useState('pseudonymize') // pseudonymize | revert
  const [batch, setBatch] = useState(null)
  const [pseudonymizedText, setPseudonymizedText] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [authUser, setAuthUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [defaultPasswordWarning, setDefaultPasswordWarning] = useState(false)
  const { showToast, ToastContainer } = useToast()

  // Ref per cancellare il polling in corso quando l'utente fa reset/logout
  // Usando un ref (non state) per evitare re-render e per essere leggibile
  // in modo sincrono all'interno del loop async senza closure stale.
  const pollingCancelledRef = useRef(false)

  useEffect(() => {
    const bootstrapAuth = async () => {
      try {
        const response = await axios.get('/api/auth/me')
        setAuthUser(response.data.username)
        if (response.data.default_password) {
          setDefaultPasswordWarning(true)
        }
      } catch {
        setAuthUser(null)
      } finally {
        setAuthLoading(false)
      }
    }
    bootstrapAuth()
  }, [])

  /**
   * Polling del batch fino a completamento (status 'done' o 'done_with_errors').
   *
   * Usa pollingCancelledRef per interrompere il loop quando l'utente fa reset
   * o logout prima che il batch sia completato, evitando state update su
   * componenti smontati e richieste HTTP inutili.
   *
   * @param {string} batchId - ID del batch da monitorare
   * @param {number} timeoutMs - Timeout massimo in ms (default: 25 minuti)
   * @param {number} intervalMs - Intervallo di polling in ms (default: 1.5s)
   * @returns {Promise<object>} - Batch completo con tutti i dati
   * @throws {Error} - Se il batch va in errore, viene cancellato o scade il timeout
   */
  const pollBatchUntilApplied = async (batchId, timeoutMs = 25 * 60 * 1000, intervalMs = 1500) => {
    const startedAt = Date.now()
    pollingCancelledRef.current = false

    while (Date.now() - startedAt < timeoutMs) {
      // Controlla la cancellazione prima di ogni richiesta HTTP
      if (pollingCancelledRef.current) {
        throw new Error('Polling cancellato dall\'utente')
      }

      const statusResponse = await axios.get(`/api/batches/${batchId}/status`)
      const currentBatch = statusResponse.data
      const status = String(currentBatch?.status || '').toLowerCase()

      if (status === 'done' || status === 'done_with_errors') {
        const fullBatchResponse = await axios.get(`/api/batches/${batchId}`)
        return fullBatchResponse.data
      }

      if (status === 'error') {
        throw new Error(currentBatch?.error_message || 'Errore durante apply del batch')
      }

      // Controlla la cancellazione anche durante l'attesa tra un poll e l'altro
      await new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, intervalMs)
        // Controlla ogni 100ms se il polling è stato cancellato
        const cancelCheck = setInterval(() => {
          if (pollingCancelledRef.current) {
            clearTimeout(timer)
            clearInterval(cancelCheck)
            reject(new Error('Polling cancellato dall\'utente'))
          }
        }, 100)
        // Pulizia del cancelCheck quando il timer scade normalmente
        setTimeout(() => clearInterval(cancelCheck), intervalMs)
      })
    }

    throw new Error('Timeout attesa completamento apply batch')
  }

  const handleLogin = async (username, password) => {
    setIsLoading(true)
    try {
      const response = await axios.post('/api/auth/login', { username, password })
      setAuthUser(response.data.username)
      if (response.data.default_password) {
        setDefaultPasswordWarning(true)
      }
      // Extract CSRF token from response header and cache it
      const csrfTokenFromResponse = response.headers['x-csrf-token']
      if (csrfTokenFromResponse) {
        setCsrfToken(csrfTokenFromResponse)
      }
      showToast('Login effettuato', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Login fallito', 'error')
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const handleLogout = async () => {
    // Cancella il polling in corso prima di fare logout
    pollingCancelledRef.current = true
    try {
      await axios.post('/api/auth/logout')
    } catch {
      // ignore
    }
    setAuthUser(null)
    setBatch(null)
    setPseudonymizedText(null)
    setCurrentStep('scanner')
    showToast('Logout effettuato', 'info')
  }

  const handleScan = (scanResult) => {
    setBatch(scanResult)
    setCurrentStep('findings')
  }

  const handleApply = async ({ batchId, fileId, isTextInput, sourceText }) => {
    setIsLoading(true)
    try {
      if (isTextInput) {
        const response = await axios.post('/api/console/apply', {
          batch_id: batchId,
          file_id: fileId,
          text: sourceText || '',
        })
        setPseudonymizedText(response.data.pseudonymized_text || '')
      } else {
        const applyResponse = await axios.post(`/api/batches/${batchId}/apply`)

        if (applyResponse.status === 202) {
          showToast('Apply accodato, attendo completamento...', 'info')
          const completedBatch = await pollBatchUntilApplied(batchId)
          setBatch((prev) => ({
            ...completedBatch,
            passphrase: prev?.passphrase,
            is_text_input: false,
          }))
        }

        setPseudonymizedText('')
      }
      setCurrentStep('results')
      showToast('Pseudonimizzazione completata', 'success')
    } catch (error) {
      // Non mostrare errore se il polling è stato cancellato intenzionalmente
      if (error.message === "Polling cancellato dall'utente") {
        return
      }
      showToast(error.response?.data?.detail || error.message || 'Errore durante l\'applicazione', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleReset = () => {
    // Cancella il polling in corso prima di resettare lo stato
    pollingCancelledRef.current = true
    setBatch(null)
    setPseudonymizedText(null)
    setCurrentStep('scanner')
  }

  const handleSwitchMode = (mode) => {
    setToolMode(mode)
    if (mode === 'pseudonymize') {
      handleReset()
    }
  }

  if (authLoading) {
    return <div className="min-h-screen bg-slate-50 dark:bg-slate-950" />
  }

  if (!authUser) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        <Header user={null} onLogout={null} onSettingsClick={() => setIsSettingsOpen(true)} />
        <main className="max-w-7xl mx-auto py-8 px-4">
          <LoginForm onLogin={handleLogin} isLoading={isLoading} />
        </main>
        <MemoizedSettingsPanel isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} showToast={showToast} />
        <ToastContainer />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Header user={authUser} onLogout={handleLogout} onSettingsClick={() => setIsSettingsOpen(true)} />

      {/* Default password warning banner */}
      {defaultPasswordWarning && (
        <div
          role="alert"
          className="bg-amber-50 dark:bg-amber-900/30 border-b border-amber-300 dark:border-amber-700"
        >
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-amber-600 dark:text-amber-400 text-xl" aria-hidden="true">&#9888;</span>
              <p className="text-sm text-amber-800 dark:text-amber-200">
                <strong>Attenzione:</strong> stai usando la password predefinita.
                Cambiala subito nelle{' '}
                <button
                  onClick={() => { setIsSettingsOpen(true); setDefaultPasswordWarning(false) }}
                  className="underline font-semibold hover:text-amber-900 dark:hover:text-amber-100 focus:outline-none focus:ring-2 focus:ring-amber-500 rounded"
                >
                  Impostazioni
                </button>
                {' '}per proteggere il sistema.
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
              toolMode === 'pseudonymize'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-200 dark:bg-slate-700'
            }`}
          >
            Pseudonimizza
          </button>
          <button
            onClick={() => handleSwitchMode('revert')}
            className={`px-4 py-2 rounded-lg font-medium ${
              toolMode === 'revert'
                ? 'bg-blue-600 text-white'
                : 'bg-slate-200 dark:bg-slate-700'
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
        <div className="flex items-center gap-3 justify-center mb-8" aria-label="Stato avanzamento">
          <div className={`px-4 py-2 rounded-lg font-medium ${
            currentStep === 'scanner' ? 'bg-blue-600 text-white' : 'bg-green-600 text-white'
          }`}>
            {currentStep === 'scanner' ? '1' : '✓'} Scansione
          </div>
          <div className="h-1 flex-1 max-w-16 bg-slate-300 dark:bg-slate-700"></div>
          <div className={`px-4 py-2 rounded-lg font-medium ${
            currentStep === 'findings' ? 'bg-blue-600 text-white' : currentStep === 'results' ? 'bg-green-600 text-white' : 'bg-slate-300 dark:bg-slate-700'
          }`}>
            {currentStep === 'results' ? '✓' : '2'} Revisione
          </div>
          <div className="h-1 flex-1 max-w-16 bg-slate-300 dark:bg-slate-700"></div>
          <div className={`px-4 py-2 rounded-lg font-medium ${
            currentStep === 'results' ? 'bg-blue-600 text-white' : 'bg-slate-300 dark:bg-slate-700'
          }`}>
            3 Risultato
          </div>
        </div>

        {/* Scanner Step */}
        {currentStep === 'scanner' && (
          <MemoizedScanner
            onScan={handleScan}
            isLoading={isLoading}
          />
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
          <>
            <MemoizedResults
              batch={batch}
              pseudonymizedText={pseudonymizedText}
              onNewScan={handleReset}
            />
          </>
        )}
          </>
        )}
      </main>

      <MemoizedSettingsPanel isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} showToast={showToast} />
      <ToastContainer />
    </div>
  )
}

export default App
