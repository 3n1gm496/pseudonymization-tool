import React, { useState, useRef } from 'react'
import axios from 'axios'
import { useToast } from '../hooks/useToast'

/**
 * @typedef {import('../types').Batch} Batch
 */

/**
 * Scanner Component - Handles text and file scanning input
 * 
 * @param {Object} props
 * @param {function(Batch): void} props.onScan - Callback when scan completes with batch data
 * @param {boolean} props.isLoading - Loading state from parent (shared across operations)
 * @returns {React.ReactElement}
 */
const Scanner = ({ onScan, isLoading }) => {
  const [text, setText] = useState('')
  const [uploadedFile, setUploadedFile] = useState(null)
  const [scanLoading, setScanLoading] = useState(false)  // ✅ FIX #6: Local loading state for scans
  const fileInputRef = useRef(null)
  const { showToast } = useToast()

  const handleTextScan = async (e) => {
    e.preventDefault()
    if (!text.trim()) {
      showToast('Inserisci del testo da scansionare', 'warning')
      return
    }

    // ✅ FIX #14: Add timeout handling for text scan
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 30000)  // 30 second timeout

    setScanLoading(true)  // ✅ Set local loading state
    try {
      const response = await axios.post(
        '/api/console/scan',
        { text },
        { signal: controller.signal }
      )
      onScan({ ...response.data, is_text_input: true, source_text: text })
      showToast('Scan completato', 'success')
    } catch (error) {
      if (error.code === 'ECONNABORTED') {
        showToast('Timeout dello scan dopo 30 secondi', 'error')
      } else {
        showToast(error.response?.data?.detail || 'Errore durante lo scan', 'error')
      }
    } finally {
      clearTimeout(timeoutId)
      setScanLoading(false)  // ✅ Always reset loading state on error or success
    }
  }

  const handleFileScan = async (e) => {
    e.preventDefault()
    if (!uploadedFile) {
      showToast('Seleziona un file', 'warning')
      return
    }

    // ✅ FIX #11a: Check file size before uploading
    const MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  // 100MB
    if (uploadedFile.size > MAX_FILE_SIZE_BYTES) {
      const fileSizeMB = (uploadedFile.size / 1024 / 1024).toFixed(1)
      const maxSizeMB = (MAX_FILE_SIZE_BYTES / 1024 / 1024).toFixed(0)
      showToast(
        `File troppo grande: ${fileSizeMB}MB (massimo ${maxSizeMB}MB)`,
        'error'
      )
      return
    }

    setScanLoading(true)  // ✅ Set local loading state
    try {
      const formData = new FormData()
      formData.append('files', uploadedFile)

      // ✅ FIX #11b: Add upload progress tracking
      const response = await axios.post('/api/batches', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (progressEvent) => {
          // Could add progress bar here if needed
          const percentComplete = Math.round(
            (progressEvent.loaded * 100) / progressEvent.total
          )
          // TODO: Update progress UI if implemented
        },
      })
      onScan({ ...response.data, is_text_input: false })
      showToast('File scansionato', 'success')
      setUploadedFile(null)
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore durante lo scan', 'error')
    } finally {
      setScanLoading(false)  // ✅ Always reset loading state on error or success
    }
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    e.currentTarget.classList.add('border-blue-500', 'bg-blue-50', 'dark:bg-blue-900/20')
  }

  const handleDragLeave = (e) => {
    e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50', 'dark:bg-blue-900/20')
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.currentTarget.classList.remove('border-blue-500', 'bg-blue-50', 'dark:bg-blue-900/20')
    const files = e.dataTransfer.files
    if (files.length > 0) {
      setUploadedFile(files[0])
    }
  }

  const handleDropzoneKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      fileInputRef.current?.click()
    }
  }

  return (
    <div className="w-full mx-auto p-6 space-y-6">
      {/* Text Input */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Testo Diretto</h2>
        <form onSubmit={handleTextScan} className="space-y-4">
          <label htmlFor="scan-text" className="sr-only">Testo da pseudonimizzare</label>
          <textarea
            id="scan-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Incolla o digita il testo da pseudonimizzare..."
            rows={6}
            maxLength={10000}
            className="w-full px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            disabled={isLoading || scanLoading}
            aria-label="Testo da pseudonimizzare"
          />
          <div className="flex justify-between items-center">
            <span className="text-sm text-slate-500 dark:text-slate-400">
              {text.length} / 10000 caratteri
            </span>
            <button
              type="submit"
              disabled={isLoading || scanLoading || !text.trim()}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading || scanLoading ? 'Scansionando...' : 'Scansiona'}
            </button>
          </div>
        </form>
      </div>

      {/* File Upload */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-4">Carica File</h2>
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={handleDropzoneKeyDown}
          className="border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg p-8 text-center cursor-pointer hover:border-blue-500 transition-colors"
          role="button"
          tabIndex={0}
          aria-label="Area caricamento file"
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.xlsx,.jpg,.png,.txt,.csv,.md"
            onChange={(e) => setUploadedFile(e.target.files?.[0] || null)}
            className="hidden"
            disabled={isLoading || scanLoading}
            aria-label="Seleziona file"
          />
          <div className="space-y-2">
            <div className="text-3xl">📁</div>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Trascina il file qui o clicca per selezionare
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              PDF, DOCX, XLSX, JPG, PNG, TXT, CSV, MD
            </p>
          </div>
        </div>
        {uploadedFile && (
          <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-300 dark:border-green-700 rounded-lg">
            <p className="text-sm text-green-800 dark:text-green-200">
              ✓ {uploadedFile.name}
            </p>
          </div>
        )}
        <div className="mt-4">
          <button
            onClick={handleFileScan}
            disabled={isLoading || scanLoading || !uploadedFile}
            className="w-full px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading || scanLoading ? 'Scansionando...' : 'Scansiona File'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default React.memo(Scanner)
