import React from 'react'
import axios from 'axios'
import { useToast } from '../hooks/useToast'
import { copyToClipboard } from '../utils/text-export'

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
  const [showPassphrase, setShowPassphrase] = React.useState(false)
  const [downloadingMapping, setDownloadingMapping] = React.useState(false)
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

  const handleDownloadMapping = async () => {
    if (!batch?.batch_id) {
      showToast('Batch non trovato', 'error')
      return
    }
    setDownloadingMapping(true)
    try {
      const response = await axios.get(`/api/console/${batch.batch_id}/mapping.enc`, {
        responseType: 'blob',
      })
      const blob = new Blob([response.data], { type: 'application/octet-stream' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `mapping_${batch.batch_id.substring(0, 8)}.enc`
      a.click()
      window.URL.revokeObjectURL(url)
      showToast('Mapping.enc scaricato', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore download mapping', 'error')
    } finally {
      setDownloadingMapping(false)
    }
  }

  const handleCopyPassphrase = async () => {
    const success = await copyToClipboard(batch?.passphrase || '')
    showToast(success ? 'Passphrase copiata negli appunti' : 'Errore copia', success ? 'success' : 'error')
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

      {/* PASSPHRASE & MAPPING - Integrato nel flusso principale */}
      <div className="bg-gradient-to-r from-orange-50 to-amber-50 dark:from-orange-900/20 dark:to-amber-900/20 rounded-lg shadow p-6 border border-orange-200 dark:border-orange-700 space-y-4">
        <h3 className="text-lg font-semibold text-orange-900 dark:text-orange-100">🔐 Passphrase e Mapping Cifrato</h3>
        
        {/* PASSPHRASE */}
        <div className="space-y-2">
          <label className="block text-sm font-semibold text-orange-800 dark:text-orange-200">Passphrase per Decifrazione</label>
          <p className="text-xs text-orange-600 dark:text-orange-300 mb-2">Salva questa passphrase. La userai per decifrare risposte AI o reversi batch.</p>
          <div className="flex gap-2">
            <input
              type={showPassphrase ? 'text' : 'password'}
              value={batch?.passphrase || ''}
              readOnly
              className="flex-1 px-3 py-2 border border-orange-300 dark:border-orange-600 rounded-lg bg-white dark:bg-slate-900 font-mono text-sm"
              placeholder="Passphrase non disponibile"
            />
            <button
              onClick={() => setShowPassphrase(!showPassphrase)}
              className="px-3 py-2 bg-orange-300 dark:bg-orange-700 rounded-lg hover:bg-orange-400 dark:hover:bg-orange-600 transition-colors"
              title={showPassphrase ? 'Nascondi' : 'Mostra'}
            >
              {showPassphrase ? '👁️' : '👁️‍🗨️'}
            </button>
            <button
              onClick={handleCopyPassphrase}
              disabled={!batch?.passphrase}
              className="px-3 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              📋 Copia
            </button>
          </div>
        </div>

        {/* MAPPING.ENC */}
        <div className="space-y-2 pt-2 border-t border-orange-200 dark:border-orange-700">
          <label className="block text-sm font-semibold text-orange-800 dark:text-orange-200">File di Mapping Cifrato</label>
          <p className="text-xs text-orange-600 dark:text-orange-300 mb-3">Scarica questo file. Serve per decifrare risposte AI o reversi batch. <b>Non inviarlo a terzi.</b></p>
          <button
            onClick={handleDownloadMapping}
            disabled={downloadingMapping || !batch?.batch_id}
            className="w-full px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-colors"
          >
            {downloadingMapping ? 'Scaricamento...' : '📥 Scarica mapping.enc'}
          </button>
        </div>

        {/* FOOTER NOTE */}
        <div className="text-xs text-orange-700 dark:text-orange-300 pt-2 border-t border-orange-200 dark:border-orange-700">
          <b>⚠️ Ricorda:</b> Conserva securely questo file e questa passphrase. Serviranno per decifrare risposte AI o reversi batch.
        </div>
      </div>
    </div>
  )
}

export default React.memo(Results)
