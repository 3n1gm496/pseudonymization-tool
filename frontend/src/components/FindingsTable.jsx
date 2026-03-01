import React, { useState } from 'react'
import axios from 'axios'
import { useToast } from '../hooks/useToast'

const FindingsTable = ({ batch, onApply, isLoading }) => {
  const [decisions, setDecisions] = useState(() => {
    return Object.fromEntries(
      batch.findings.map((f) => [
        f.finding_id,
        {
          action: 'accept',
          custom_pseudonym: f.proposed_pseudonym,
        },
      ])
    )
  })
  const { showToast } = useToast()

  const handleActionChange = (findingId, action) => {
    setDecisions((prev) => ({
      ...prev,
      [findingId]: { ...prev[findingId], action },
    }))
  }

  const handleCustomPseudonymChange = (findingId, value) => {
    setDecisions((prev) => ({
      ...prev,
      [findingId]: { ...prev[findingId], custom_pseudonym: value },
    }))
  }

  const handleApply = async () => {
    try {
      const reviewItems = Object.entries(decisions).map(([findingId, { action, custom_pseudonym }]) => ({
        finding_id: findingId,
        action,
        modified_pseudonym: custom_pseudonym,
      }))

      await axios.post(`/api/batches/${batch.batch_id}/review`, {
        decisions: reviewItems,
      })

      const fileId = batch.file_id || batch.files?.[0]?.id || batch.files?.[0]?.file_id
      await onApply({
        batchId: batch.batch_id,
        fileId,
        isTextInput: !!batch.is_text_input,
        sourceText: batch.source_text || '',
      })
      showToast('Pseudonimizzazione applicata', 'success')
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore durante l\'applicazione', 'error')
    }
  }

  const getSafetyColor = (label) => {
    const colors = {
      SAFE_TO_UPLOAD: 'text-green-600 dark:text-green-400',
      CAUTION: 'text-yellow-600 dark:text-yellow-400',
      UNSAFE: 'text-red-600 dark:text-red-400',
    }
    return colors[label] || 'text-slate-600'
  }

  const getConfidenceColor = (score) => {
    if (score >= 0.9) return 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
    if (score >= 0.7) return 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200'
    return 'bg-orange-100 dark:bg-orange-900 text-orange-800 dark:text-orange-200'
  }

  return (
    <div className="w-full mx-auto p-6 space-y-6">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow overflow-hidden">
        <div className="p-6 border-b border-slate-200 dark:border-slate-700">
          <div className="flex justify-between items-center gap-4">
            <div>
              <h2 className="text-lg font-semibold">Entità Rilevate</h2>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                {batch.findings.length} entità trovate
              </p>
            </div>
            <div className={`text-lg font-semibold ${getSafetyColor(batch.safety_label)}`}>
              {batch.safety_label}
            </div>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">Tabella findings con decisioni di review</caption>
            <thead className="bg-slate-50 dark:bg-slate-900 border-b border-slate-200 dark:border-slate-700">
              <tr>
                <th scope="col" className="px-4 py-3 text-left font-semibold">Tipo</th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">Valore Originale</th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">Proposta</th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">Personalizzazione</th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">Confidenza</th>
                <th scope="col" className="px-4 py-3 text-left font-semibold">Azione</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
              {batch.findings.map((finding) => (
                <tr key={finding.finding_id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                  <td className="px-4 py-3 font-medium text-blue-600 dark:text-blue-400">
                    {finding.entity_type}
                  </td>
                  <td className="px-4 py-3 text-slate-600 dark:text-slate-400 font-mono text-xs">
                    {finding.original_value}
                  </td>
                  <td className="px-4 py-3 text-green-600 dark:text-green-400 font-mono text-xs">
                    {finding.proposed_pseudonym}
                  </td>
                  <td className="px-4 py-3">
                    <input
                      type="text"
                      value={decisions[finding.finding_id]?.custom_pseudonym || ''}
                      onChange={(e) =>
                        handleCustomPseudonymChange(finding.finding_id, e.target.value)
                      }
                      className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Personalizza..."
                      disabled={isLoading}
                      aria-label={`Pseudonimo personalizzato per ${finding.entity_type}`}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${getConfidenceColor(
                        finding.confidence_score
                      )}`}
                    >
                      {(finding.confidence_score * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={decisions[finding.finding_id]?.action || 'accept'}
                      onChange={(e) =>
                        handleActionChange(finding.finding_id, e.target.value)
                      }
                      className="px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      disabled={isLoading}
                      aria-label={`Azione review per ${finding.entity_type}`}
                    >
                      <option value="accept">Accetta</option>
                      <option value="reject">Rifiuta</option>
                      <option value="modify">Modifica</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-700 flex justify-end">
          <button
            onClick={handleApply}
            disabled={isLoading}
            className="px-6 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Applicazione in corso...' : 'Applica Pseudonimizzazione'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default FindingsTable
