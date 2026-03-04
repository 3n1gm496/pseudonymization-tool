import { useMemo, useState, type JSX, type FormEvent, type ChangeEvent } from 'react'
import axios from '../utils/axios'
import { copyToClipboard, downloadTextFile } from '../utils/text-export'
import type { ToastType } from '../types'

interface DecipherAIResponseProps {
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  showToast: (message: string, type?: ToastType) => void
}

interface PreviewMatch {
  pseudonym: string
  matches: number
}

interface PreviewResult {
  mapping_entries: number
  input_chars: number
  total_matches: number
  sample_matches?: PreviewMatch[]
}

interface ApplyResult {
  reverted_text?: string
  total_replacements?: number
}

const DecipherAIResponse = ({ isLoading, setIsLoading, showToast }: DecipherAIResponseProps): JSX.Element => {
  const [mappingFile, setMappingFile] = useState<File | null>(null)
  const [passphrase, setPassphrase] = useState('')
  const [aiText, setAiText] = useState('')
  const [showPassphrase, setShowPassphrase] = useState(false)
  const [preview, setPreview] = useState<PreviewResult | null>(null)
  const [decodedText, setDecodedText] = useState('')

  const canSubmit = useMemo(
    () => mappingFile !== null && passphrase.trim().length > 0 && aiText.trim().length > 0,
    [mappingFile, passphrase, aiText],
  )

  const handlePreview = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!canSubmit) return
    setIsLoading(true)
    try {
      const formData = new FormData()
      formData.append('mapping_file', mappingFile as File)
      formData.append('passphrase', passphrase)
      formData.append('text', aiText)
      const response = await axios.post<PreviewResult>('/api/revert/text/preview', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setPreview(response.data)
      showToast('Preview completato', 'success')
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      showToast(axiosError.response?.data?.detail ?? 'Errore preview', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleApply = async (): Promise<void> => {
    if (!canSubmit) return
    setIsLoading(true)
    try {
      const formData = new FormData()
      formData.append('mapping_file', mappingFile as File)
      formData.append('passphrase', passphrase)
      formData.append('text', aiText)
      const response = await axios.post<ApplyResult>('/api/revert/text/apply', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setDecodedText(response.data.reverted_text ?? '')
      showToast(
        `Decifratura completata (${response.data.total_replacements ?? 0} sostituzioni)`,
        'success',
      )
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      showToast(axiosError.response?.data?.detail ?? 'Errore decifratura', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCopyDecoded = async (): Promise<void> => {
    const success = await copyToClipboard(decodedText)
    showToast(success ? 'Copiato negli appunti' : 'Errore copia', success ? 'success' : 'error')
  }

  const handleDownloadDecoded = (): void => {
    downloadTextFile(decodedText, 'ai-response-deciphered.txt')
    showToast('Risposta scaricata', 'success')
  }

  return (
    <div className="w-full mx-auto p-6 space-y-6">
      {/* INFO */}
      <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="font-semibold text-blue-900 dark:text-blue-100 mb-2">ℹ️ Decifratura risposta AI</h3>
        <p className="text-sm text-blue-800 dark:text-blue-200">
          Carica il mapping.enc che hai scaricato, inserisci la passphrase originale, incolla la
          risposta pseudonimizzata dell&apos;AI e ottieni il testo con dati reali.
        </p>
      </div>
      {/* INPUT FORM */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <form onSubmit={(e) => void handlePreview(e)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">File mapping.enc</label>
            <input
              type="file"
              accept=".enc"
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setMappingFile(e.target.files?.[0] ?? null)
              }
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
              disabled={isLoading}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Usa lo stesso mapping.enc scaricato dal flusso &quot;Prepara per AI&quot;
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
                placeholder="Inserisci la passphrase originale"
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
          <div>
            <label className="block text-sm font-medium mb-2">Risposta AI (pseudonimizzata)</label>
            <textarea
              value={aiText}
              onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setAiText(e.target.value)}
              rows={8}
              className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
              disabled={isLoading}
              placeholder="Incolla qui la risposta pseudonimizzata dell'AI"
            />
          </div>
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={isLoading || !canSubmit}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              {isLoading ? 'Analisi...' : '🔍 Preview'}
            </button>
            <button
              type="button"
              onClick={() => void handleApply()}
              disabled={isLoading || !canSubmit}
              className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50"
            >
              {isLoading ? 'Decifratura...' : '🔓 Decifra'}
            </button>
          </div>
        </form>
      </div>
      {/* PREVIEW STATS */}
      {preview && (
        <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
          <h4 className="font-semibold mb-2">Analisi Preview</h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Mapping entries</div>
              <div className="text-lg font-bold">{preview.mapping_entries}</div>
            </div>
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Caratteri input</div>
              <div className="text-lg font-bold">{preview.input_chars}</div>
            </div>
            <div className="bg-white dark:bg-slate-800 p-3 rounded">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Match trovati</div>
              <div className="text-lg font-bold text-green-600">{preview.total_matches}</div>
            </div>
            {(preview.sample_matches?.length ?? 0) > 0 && (
              <div className="bg-white dark:bg-slate-800 p-3 rounded">
                <div className="text-xs font-medium text-slate-600 dark:text-slate-400">Pseudonimi rilevati</div>
                <div className="text-sm">{preview.sample_matches?.length ?? 0} tipi</div>
              </div>
            )}
          </div>
          {(preview.sample_matches?.length ?? 0) > 0 && (
            <div className="mt-3">
              <div className="text-xs font-medium text-slate-600 dark:text-slate-400 mb-2">
                Esempi pseudonimi trovati:
              </div>
              <ul className="text-xs space-y-1 ml-4 text-slate-700 dark:text-slate-300">
                {preview.sample_matches?.map((m, i) => (
                  <li key={i}>• {m.pseudonym} ({m.matches}x)</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      {/* RISULTATO DECIFRATO */}
      {decodedText && (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
          <h4 className="text-lg font-semibold mb-3">Risposta decifrata</h4>
          <textarea
            readOnly
            value={decodedText}
            rows={10}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-slate-50 dark:bg-slate-900 font-mono text-sm"
          />
          <div className="flex gap-3 mt-4">
            <button
              onClick={() => void handleCopyDecoded()}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg"
            >
              📋 Copia negli appunti
            </button>
            <button
              onClick={handleDownloadDecoded}
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg"
            >
              ⬇️ Scarica .txt
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default DecipherAIResponse
