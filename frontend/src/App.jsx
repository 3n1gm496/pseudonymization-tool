import React, { useState } from 'react'
import axios from 'axios'
import Header from './components/Header'
import PolicySelector from './components/PolicySelector'
import Scanner from './components/Scanner'
import FindingsTable from './components/FindingsTable'
import Results from './components/Results'
import { useToast } from './hooks/useToast'

const App = () => {
  const [currentStep, setCurrentStep] = useState('scanner') // scanner | findings | results
  const [selectedPolicy, setSelectedPolicy] = useState('SOC_LOGS')
  const [batch, setBatch] = useState(null)
  const [pseudonymizedText, setPseudonymizedText] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const { showToast, ToastContainer } = useToast()

  const handleScan = (scanResult) => {
    setBatch(scanResult)
    setCurrentStep('findings')
  }

  const handleApply = async (batchId, fileId) => {
    setIsLoading(true)
    try {
      const response = await axios.post(`/api/batches/${batchId}/apply`, {
        file_id: fileId,
      })
      setPseudonymizedText(response.data.pseudonymized_text)
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

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Header />

      <main className="max-w-7xl mx-auto py-8 px-4 space-y-8">
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

        {/* Policy Selector - Always visible */}
        <PolicySelector selectedPolicy={selectedPolicy} onPolicyChange={setSelectedPolicy} />

        {/* Scanner Step */}
        {currentStep === 'scanner' && (
          <Scanner
            onScan={handleScan}
            selectedPolicy={selectedPolicy}
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
