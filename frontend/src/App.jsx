import React, { useEffect, useState } from 'react'
import axios from 'axios'
import Header from './components/Header'
import Scanner from './components/Scanner'
import FindingsTable from './components/FindingsTable'
import Results from './components/Results'
import { useToast } from './hooks/useToast'
import LoginForm from './components/LoginForm'

const App = () => {
  axios.defaults.withCredentials = true

  const [currentStep, setCurrentStep] = useState('scanner') // scanner | findings | results
  const [batch, setBatch] = useState(null)
  const [pseudonymizedText, setPseudonymizedText] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [authUser, setAuthUser] = useState(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [authWarning, setAuthWarning] = useState('')
  const { showToast, ToastContainer } = useToast()

  useEffect(() => {
    const bootstrapAuth = async () => {
      try {
        const response = await axios.get('/api/auth/me')
        setAuthUser(response.data.username)
        if (response.data.default_password) {
          setAuthWarning('Stai usando la password di default: cambiala via AUTH_PASSWORD.')
        }
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
      if (response.data.default_password) {
        setAuthWarning('Stai usando la password di default: cambiala via AUTH_PASSWORD.')
      } else {
        setAuthWarning('')
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

  if (authLoading) {
    return <div className="min-h-screen bg-slate-50 dark:bg-slate-950" />
  }

  if (!authUser) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
        <Header user={null} onLogout={null} />
        <main className="max-w-7xl mx-auto py-8 px-4">
          <LoginForm onLogin={handleLogin} isLoading={isLoading} />
        </main>
        <ToastContainer />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Header user={authUser} onLogout={handleLogout} />

      <main className="max-w-7xl mx-auto py-8 px-4 space-y-8">
        {authWarning && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-300 dark:border-yellow-700 text-yellow-900 dark:text-yellow-200 px-4 py-3 rounded-lg">
            {authWarning}
          </div>
        )}
        {/* Progress Bar */}
        {(currentStep === 'findings' || currentStep === 'results') && (
          <div className="flex items-center gap-4 justify-center mb-8">
            <div className={`px-4 py-2 rounded-lg font-medium ${
              currentStep === 'scanner' ? 'bg-blue-600 text-white' : 'bg-green-600 text-white'
            }`}>
              ✓ Scansione
            </div>
            <div className="h-1 flex-1 bg-slate-300 dark:bg-slate-700"></div>
            <div className={`px-4 py-2 rounded-lg font-medium ${
              currentStep === 'findings' ? 'bg-blue-600 text-white' : 'bg-green-600 text-white'
            }`}>
              {currentStep === 'results' ? '✓' : '2'} Revisione
            </div>
            <div className="h-1 flex-1 bg-slate-300 dark:bg-slate-700"></div>
            <div className={`px-4 py-2 rounded-lg font-medium ${
              currentStep === 'results' ? 'bg-blue-600 text-white' : 'bg-slate-300 dark:bg-slate-700'
            }`}>
              3 Risultato
            </div>
          </div>
        )}

        {/* Scanner Step */}
        {currentStep === 'scanner' && (
          <Scanner
            onScan={handleScan}
            isLoading={isLoading}
          />
        )}

        {/* Findings Review Step */}
        {currentStep === 'findings' && batch && (
          <FindingsTable
            batch={batch}
            onApply={handleApply}
            isLoading={isLoading}
          />
        )}

        {/* Results Step */}
        {currentStep === 'results' && batch && (
          <>
            <Results
              batch={batch}
              pseudonymizedText={pseudonymizedText}
            />
            <div className="text-center">
              <button
                onClick={handleReset}
                className="px-8 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
              >
                ← Torna al Nuovo Scan
              </button>
            </div>
          </>
        )}
      </main>

      <ToastContainer />
    </div>
  )
}

export default App
