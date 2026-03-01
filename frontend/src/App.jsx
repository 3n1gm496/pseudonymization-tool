import React, { useEffect, useState } from 'react'
import axios from 'axios'
import Header from './components/Header'
import Scanner from './components/Scanner'
import FindingsTable from './components/FindingsTable'
import Results from './components/Results'
import RevertPanel from './components/RevertPanel'
import SettingsPanel from './components/SettingsPanel'
import { useToast } from './hooks/useToast'
import LoginForm from './components/LoginForm'

// ✅ FIX #13: Memoize heavy components to prevent unnecessary re-renders
const MemoizedScanner = React.memo(Scanner)
const MemoizedFindingsTable = React.memo(FindingsTable)
const MemoizedResults = React.memo(Results)
const MemoizedRevertPanel = React.memo(RevertPanel)
const MemoizedSettingsPanel = React.memo(SettingsPanel)

const App = () => {
  axios.defaults.withCredentials = true

  const [currentStep, setCurrentStep] = useState('scanner') // scanner | findings | results
  const [toolMode, setToolMode] = useState('pseudonymize') // pseudonymize | revert
  const [batch, setBatch] = useState(null)
  const [pseudonymizedText, setPseudonymizedText] = useState(null)
  const [passphrase, setPassphrase] = useState(null) // Passphrase dalla pseudonimizzazione completata
  const [isLoading, setIsLoading] = useState(false)
  const [authUser, setAuthUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const { showToast, ToastContainer } = useToast()

  useEffect(() => {
    const bootstrapAuth = async () => {
      try {
        const response = await axios.get('/api/auth/me')
        setAuthUser(response.data.username)
      } catch {
        setAuthUser(null)
      } finally {
        setAuthLoading(false)
      }
    }
    bootstrapAuth()
  }, [])

  const handleLogin = async (username, password) => {
    setIsLoading(true)
    try {
      const response = await axios.post('/api/auth/login', { username, password })
      setAuthUser(response.data.username)
      showToast('Login effettuato', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Login fallito', 'error')
      throw error
    } finally {
      setIsLoading(false)
    }
  }

  const handleLogout = async () => {
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
        await axios.post(`/api/batches/${batchId}/apply`)
        setPseudonymizedText('')
      }
      setCurrentStep('results')
      showToast('Pseudonimizzazione completata', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore durante l\'applicazione', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleReset = () => {
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
