import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { copyToClipboard, downloadTextFile } from '../utils/text-export'

const PrepareForAI = ({ batch, pseudonymizedText, isLoading, setIsLoading, showToast }) => {
  const [passphrase, setPassphrase] = useState('')
  const [showPassphrase, setShowPassphrase] = useState(false)

  // Popola la passphrase dal batch quando il componente monta o il batch cambia
  useEffect(() => {
    if (batch?.passphrase) {
      setPassphrase(batch.passphrase)
    }
  }, [batch?.passphrase])
  const [downloadingMapping, setDownloadingMapping] = useState(false)

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

  const handleCopyText = async () => {
    const success = await copyToClipboard(pseudonymizedText)
    showToast(success ? 'Copiato negli appunti' : 'Errore copia', success ? 'success' : 'error')
  }

  const handleCopyPassphrase = async () => {
    const success = await copyToClipboard(passphrase)
    showToast(success ? 'Passphrase copiata' : 'Errore copia', success ? 'success' : 'error')
  }

  const handleDownloadText = () => {
    downloadTextFile(
      pseudonymizedText,
      `pseudonymized_${batch?.batch_id?.substring(0, 8) || 'batch'}.txt`
    )
    showToast('Testo scaricato', 'success')
  }

  if (!batch || !pseudonymizedText) {
    return (
      <div className="w-full mx-auto p-6 bg-white dark:bg-slate-800 rounded-lg shadow">
        <h2 className="text-xl font-semibold mb-2">Prepara per AI</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Completa il flusso di pseudonimizzazione (Scansione → Revisione → Apply) per preparare il testo.
        </p>
      </div>
    )
  }

  return (
    <div className="w-full mx-auto p-6 space-y-6">
      {/* INFO SECTION */}
      <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">ℹ️ Come procedere</h3>
        <ol className="list-decimal list-inside text-sm text-blue-800 dark:text-blue-200 space-y-1">
          <li>Scarica il testo pseudonimizzato qui sotto</li>
          <li>Scarica il file <code className="bg-blue-100 dark:bg-blue-900 px-1 rounded">mapping.enc</code> (contiene la cifratura)</li>
          <li>Copia la passphrase (serve per decifrare dopo)</li>
          <li>Invia il testo all&apos;AI (il mapping.enc NON lo invii)</li>
          <li>Quando ricevi la risposta, vai in &quot;Decifra risposta AI&quot; con lo stesso mapping.enc</li>
        </ol>
      </div>

      {/* TESTO PSEUDONIMIZZATO */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-3">Testo pseudonimizzato per AI</h3>
        <textarea
          readOnly
          value={pseudonymizedText}
          rows={12}
          className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-slate-50 dark:bg-slate-900 font-mono text-sm"
        />
        <div className="flex gap-3 mt-4">
          <button
            onClick={handleCopyText}
            disabled={isLoading}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg disabled:opacity-50"
          >
            📋 Copia negli appunti
          </button>
          <button
            onClick={handleDownloadText}
            disabled={isLoading}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg disabled:opacity-50"
          >
            ⬇️ Scarica .txt
          </button>
        </div>
      </div>

      {/* MAPPING.ENC */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-3">File di mapping (cifrato)</h3>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Scarica questo file. Serve per decifrare la risposta dell&apos;AI. <b>Non inviarlo all&apos;AI.</b>
        </p>
        <button
          onClick={handleDownloadMapping}
          disabled={downloadingMapping || !batch?.batch_id}
          className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50"
        >
          {downloadingMapping ? 'Download...' : '📥 Scarica mapping.enc'}
        </button>
      </div>

      {/* PASSPHRASE */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold mb-3">Passphrase di decifrazione</h3>
        <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
          Salva questa passphrase. La userai per decifrare la risposta dell&apos;AI.
        </p>
        <div className="flex gap-2 mb-4">
          <input
            type={showPassphrase ? 'text' : 'password'}
            value={passphrase}
            readOnly
            className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-slate-50 dark:bg-slate-900 font-mono"
            placeholder="La passphrase verrà visualizzata automaticamente"
          />
          <button
            onClick={() => setShowPassphrase(!showPassphrase)}
            className="px-3 py-2 bg-slate-300 dark:bg-slate-600 rounded-lg hover:bg-slate-400 dark:hover:bg-slate-500"
          >
            {showPassphrase ? '👁️' : '👁️‍🗨️'}
          </button>
        </div>
        <button
          onClick={handleCopyPassphrase}
          disabled={!passphrase}
          className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg disabled:opacity-50"
        >
          🔑 Copia passphrase
        </button>
      </div>

      {/* NOTE FINALI */}
      <div className="bg-amber-50 dark:bg-amber-900/30 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
        <p className="text-sm text-amber-800 dark:text-amber-200">
          <b>⚠️ Ricorda:</b> quando ricevi la risposta pseudonimizzata dall&apos;AI, usa <b>lo stesso</b> mapping.enc e passphrase per decifrare.
        </p>
      </div>
    </div>
  )
}

export default PrepareForAI
