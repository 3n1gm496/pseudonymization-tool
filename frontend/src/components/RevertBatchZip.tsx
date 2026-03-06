import { useMemo, useState, type JSX, type FormEvent, type ChangeEvent } from 'react'
import axios from '../utils/axios'
import { downloadBinaryFile } from '../utils/text-export'
import type { ToastType } from '../types'

interface RevertBatchZipProps {
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  showToast: (message: string, type?: ToastType) => void
}

interface SampleMatch {
  file: string
  matches: number
}

interface PreviewResult {
  mapping_entries: number
  files_scanned: number
  text_files_scanned: number
  total_matches: number
  sample_matches?: SampleMatch[]
}

const RevertBatchZip = ({ isLoading, setIsLoading, showToast }: RevertBatchZipProps): JSX.Element => {
  const [archive, setArchive] = useState<File | null>(null)
  const [passphrase, setPassphrase] = useState('')
  const [showPassphrase, setShowPassphrase] = useState(false)
  const [preview, setPreview] = useState<PreviewResult | null>(null)

  const canSubmit = useMemo(
    () => archive !== null && passphrase.trim().length > 0,
    [archive, passphrase],
  )

  const handlePreview = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!canSubmit) return
    setIsLoading(true)
    try {
      const formData = new FormData()
      formData.append('archive', archive as File)
      formData.append('passphrase', passphrase)
      const response = await axios.post<PreviewResult>('/api/revert/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setPreview(response.data)
      showToast('Preview revert completata', 'success')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      showToast(axiosError.response?.data?.detail ?? 'Errore preview revert', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleApply = async (): Promise<void> => {
    if (!canSubmit) return
    setIsLoading(true)
    try {
      const formData = new FormData()
      formData.append('archive', archive as File)
      formData.append('passphrase', passphrase)
      const response = await axios.post('/api/revert/apply', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        responseType: 'blob',
      })
      const blob = new Blob([response.data as BlobPart], { type: 'application/zip' })
      const disposition = (response.headers['content-disposition'] as string | undefined) ?? ''
      const match = disposition.match(/filename="([^"]+)"/)
      const filename = match?.[1] ?? 'reverted_batch.zip'
      downloadBinaryFile(blob, filename)
      showToast('Revert completato: ZIP scaricato', 'success')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      showToast(axiosError.response?.data?.detail ?? 'Errore apply revert', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="w-full mx-auto p-6 space-y-6">
      <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">ℹ️ Revert batch ZIP</h3>
        <p className="text-sm text-blue-800 dark:text-blue-200">
          Carica lo <strong>ZIP scaricato al termine della pseudonimizzazione</strong> — sia dal flusso
          file che dal flusso testo. Lo ZIP contiene i file pseudonimizzati (o il TXT) e il{' '}
          <code className="bg-blue-100 dark:bg-blue-900 px-1 rounded">mapping.enc</code>.
          Inserisci la passphrase e scarica lo ZIP con i dati originali ripristinati.
        </p>
      </div>
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <form onSubmit={(e) => void handlePreview(e)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Archivio ZIP (dal tool)</label>
            <input
              type="file"
              accept=".zip"
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setArchive(e.target.files?.[0] ?? null)
              }
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
              disabled={isLoading}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Es: <code>pseudonymized-batch-abc123.zip</code> (flusso file) o{' '}
              <code>pseudonymized-console-abc123.zip</code> (flusso testo)
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Passphrase</label>
            <div className="flex gap-2">
              <input
                type={showPassphrase ? 'text' : 'password'}
                value={passphrase}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setPassphrase(e.target.value)}
                className="flex-1 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
                disabled={isLoading}
                placeholder="Inserisci passphrase"
              />
              <button
                type="button"
                onClick={() => setShowPassphrase((prev) => !prev)}
                className="px-3 py-2 bg-slate-300 dark:bg-slate-600 rounded-lg hover:bg-slate-400 dark:hover:bg-slate-500"
              >
                {showPassphrase ? '👁️' : '👁️‍🗨️'}
              </button>
            </div>
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={isLoading || !canSubmit}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              {isLoading ? 'Analisi...' : '🔍 Preview Match'}
            </button>
            <button
              type="button"
              onClick={() => void handleApply()}
              disabled={isLoading || !canSubmit}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50"
            >
              {isLoading ? 'Revert...' : '🔓 Apply Revert & Download ZIP'}
            </button>
          </div>
        </form>
      </div>
      {/* PREVIEW STATS */}
      {preview && (
        <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
          <h4 className="font-semibold mb-3">Anteprima Revert</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Mapping entries</div>
              <div className="text-lg font-bold">{preview.mapping_entries}</div>
            </div>
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">File scanditi</div>
              <div className="text-lg font-bold">{preview.files_scanned}</div>
            </div>
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">File testuali</div>
              <div className="text-lg font-bold">{preview.text_files_scanned}</div>
            </div>
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Match totali</div>
              <div className="text-lg font-bold text-green-600">{preview.total_matches}</div>
            </div>
          </div>
          {(preview.sample_matches?.length ?? 0) > 0 && (
            <div>
              <h5 className="text-sm font-medium mb-2">Esempi file con match:</h5>
              <ul className="list-disc ml-5 text-sm space-y-1 text-slate-700 dark:text-slate-300">
                {preview.sample_matches?.map((row, idx) => (
                  <li key={`${row.file}-${idx}`}>
                    {row.file} — {row.matches} match
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default RevertBatchZip
