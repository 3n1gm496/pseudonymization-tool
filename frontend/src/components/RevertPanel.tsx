import { useState, type JSX } from 'react'
import DecipherAIResponse from './DecipherAIResponse'
import RevertBatchZip from './RevertBatchZip'
import type { Batch, ToastType } from '../types'

type RevertMode = 'zip' | 'text' | null

interface RevertPanelProps {
  batch?: Batch | null
  pseudonymizedText?: string | null
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  showToast: (message: string, type?: ToastType) => void
}

const RevertPanel = ({
  batch: _batch,
  pseudonymizedText: _pseudonymizedText,
  isLoading,
  setIsLoading,
  showToast,
}: RevertPanelProps): JSX.Element => {
  const [mode, setMode] = useState<RevertMode>(null)

  // Step 1: selezione guidata
  if (mode === null) {
    return (
      <div className="w-full space-y-6">
        {/* Titolo */}
        <div className="text-center">
          <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100">
            Cosa vuoi ripristinare?
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Scegli in base a cosa hai scaricato al termine della pseudonimizzazione.
          </p>
        </div>

        {/* Scelta guidata */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl mx-auto">
          {/* Opzione A: ZIP */}
          <button
            onClick={() => setMode('zip')}
            className="group flex flex-col items-start gap-3 p-6 bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 rounded-xl hover:border-blue-500 dark:hover:border-blue-400 hover:shadow-md transition-all text-left"
          >
            <div className="text-4xl">📦</div>
            <div>
              <div className="font-semibold text-slate-800 dark:text-slate-100 group-hover:text-blue-600 dark:group-hover:text-blue-400">
                Ho lo ZIP del tool
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Hai scaricato il file{' '}
                <code className="bg-slate-100 dark:bg-slate-700 px-1 rounded text-xs">
                  pseudonymized-*.zip
                </code>{' '}
                al termine della pseudonimizzazione (flusso file o flusso testo).
              </div>
            </div>
            <div className="mt-auto text-xs font-medium text-blue-600 dark:text-blue-400 group-hover:underline">
              Ripristina file o testo dallo ZIP →
            </div>
          </button>

          {/* Opzione B: mapping.enc + testo */}
          <button
            onClick={() => setMode('text')}
            className="group flex flex-col items-start gap-3 p-6 bg-white dark:bg-slate-800 border-2 border-slate-200 dark:border-slate-700 rounded-xl hover:border-purple-500 dark:hover:border-purple-400 hover:shadow-md transition-all text-left"
          >
            <div className="text-4xl">🔑</div>
            <div>
              <div className="font-semibold text-slate-800 dark:text-slate-100 group-hover:text-purple-600 dark:group-hover:text-purple-400">
                Ho il mapping.enc + testo
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                Hai il file{' '}
                <code className="bg-slate-100 dark:bg-slate-700 px-1 rounded text-xs">
                  mapping.enc
                </code>{' '}
                separato e vuoi decifra una risposta AI o un testo pseudonimizzato.
              </div>
            </div>
            <div className="mt-auto text-xs font-medium text-purple-600 dark:text-purple-400 group-hover:underline">
              Decifra testo con mapping.enc →
            </div>
          </button>
        </div>

        {/* Nota informativa */}
        <div className="max-w-3xl mx-auto bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
          <p className="text-sm text-amber-800 dark:text-amber-200">
            <strong>Non hai lo ZIP?</strong> Torna alla schermata dei risultati della
            pseudonimizzazione e scarica il file ZIP — contiene tutto il necessario per il
            ripristino.
          </p>
        </div>
      </div>
    )
  }

  // Step 2: form specifico con breadcrumb per tornare indietro
  return (
    <div className="w-full space-y-4">
      {/* Breadcrumb / back */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setMode(null)}
          className="flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 transition-colors"
          disabled={isLoading}
        >
          ← Torna alla scelta
        </button>
        <span className="text-slate-300 dark:text-slate-600">/</span>
        <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
          {mode === 'zip' ? '📦 Ripristino da ZIP' : '🔑 Decifratura testo'}
        </span>
      </div>

      {/* Componente specifico */}
      {mode === 'zip' ? (
        <RevertBatchZip
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          showToast={showToast}
        />
      ) : (
        <DecipherAIResponse
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          showToast={showToast}
        />
      )}
    </div>
  )
}

export default RevertPanel
