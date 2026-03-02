import React from 'react'
import axios from 'axios'
import { useToast } from '../hooks/useToast'
import PrepareForAI from './PrepareForAI'

/**
 * @typedef {import('../types').Batch} Batch
 */

/**
 * Results Component - Displays pseudonymization results and download options
 * 
 * @param {Object} props
 * @param {Batch} props.batch - Batch data with findings and status
 * @param {string} props.pseudonymizedText - Pseudonymized text output (for text scans)
 * @param {function(): void} props.onNewScan - Callback to start a new scan
 * @returns {React.ReactElement}
 */
const Results = ({ batch, pseudonymizedText, onNewScan }) => {
  const { showToast } = useToast()
  const [copied, setCopied] = React.useState(false)
  const isTextFlow = !!batch?.is_text_input

  const handleCopy = () => {
    navigator.clipboard.writeText(pseudonymizedText || '')
    setCopied(true)
    showToast('Testo copiato negli appunti', 'success')
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = async () => {
    try {
      const response = await axios.get(`/api/batches/${batch.batch_id}/download`, {
        responseType: 'blob',
      })
      const url = window.URL.createObjectURL(response.data)
      const a = document.createElement('a')
      a.href = url
      a.download = `pseudonymized-batch-${batch.batch_id.slice(0, 8)}.zip`
      a.click()
      showToast('Download completato', 'success')
    } catch (error) {
      showToast('Errore durante il download', 'error')
    }
  }

  const handleDownloadText = () => {
    const textContent = pseudonymizedText || ''
    const blob = new Blob([textContent], { type: 'text/plain;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pseudonymized-${batch.batch_id.slice(0, 8)}.txt`
    a.click()
    window.URL.revokeObjectURL(url)
    showToast('Download TXT completato', 'success')
  }

  const canShowText = typeof pseudonymizedText === 'string' && pseudonymizedText.length > 0

  return (
    <div className="w-full mx-auto p-6 space-y-6">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow overflow-hidden">
        <div className="p-6 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold mb-2">Risultato Pseudonimizzazione</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Batch ID: <code className="font-mono text-xs bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded">{batch.batch_id.slice(0, 8)}...{batch.batch_id.slice(-8)}</code>
          </p>
        </div>

        <div className="p-6 space-y-4">
          {canShowText && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-semibold mb-2">Testo Pseudonimizzato</label>
              <div className="relative">
                <textarea
                  readOnly
                  value={pseudonymizedText}
                  rows={8}
                  className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-slate-50 dark:bg-slate-700 text-slate-900 dark:text-white font-mono text-sm resize-none"
                />
                <button
                  onClick={handleCopy}
                  className="absolute top-2 right-2 px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm transition-colors"
                >
                  {copied ? '✓ Copiato' : 'Copia'}
                </button>
              </div>
            </div>
          </div>
          )}

          <div className="flex gap-3">
            {!isTextFlow ? (
              <button
                onClick={handleDownload}
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors"
              >
                📥 Scarica ZIP
              </button>
            ) : (
              <button
                onClick={handleDownloadText}
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium transition-colors"
              >
                📥 Scarica TXT
              </button>
            )}
            <button
              onClick={onNewScan}
              className="flex-1 px-4 py-2 bg-slate-600 hover:bg-slate-700 text-white rounded-lg font-medium transition-colors"
              aria-label="Avvia una nuova scansione"
            >
              🔄 Nuovo Scan
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4 border border-blue-200 dark:border-blue-800">
          <div className="text-sm font-semibold text-blue-900 dark:text-blue-200">Entità Pseudonimizzate</div>
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 mt-1">{batch.findings.length}</div>
        </div>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 border border-green-200 dark:border-green-800">
          <div className="text-sm font-semibold text-green-900 dark:text-green-200">Safety Label</div>
          <div className="text-lg font-bold text-green-600 dark:text-green-400 mt-1">{batch.safety_label}</div>
        </div>
        <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4 border border-purple-200 dark:border-purple-800">
          <div className="text-sm font-semibold text-purple-900 dark:text-purple-200">Modalità</div>
          <div className="text-lg font-bold text-purple-600 dark:text-purple-400 mt-1">
            {batch.is_text_input ? '📝 Testo' : '📄 File'}
          </div>
        </div>
      </div>

      {/* Sezione Prepara per AI - ora integrata nel flusso principale */}
      <PrepareForAI 
        batch={batch} 
        pseudonymizedText={pseudonymizedText} 
        isLoading={false} 
        setIsLoading={() => {}} 
        showToast={showToast} 
      />
    </div>
  )
}

export default React.memo(Results)
