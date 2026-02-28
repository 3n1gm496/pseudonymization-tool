import React, { useEffect, useState } from 'react'
import axios from 'axios'

const PolicySelector = ({ selectedPolicy, onPolicyChange }) => {
  const [policies, setPolicies] = useState([])
  const [policyDetails, setPolicyDetails] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchPolicies = async () => {
      try {
        const response = await axios.get('/api/settings/policies')
        setPolicies(response.data.presets || [])
        if (response.data.presets?.[0]) {
          onPolicyChange(response.data.presets[0])
        }
      } catch (error) {
        console.error('Errore nel caricamento delle policy:', error)
      } finally {
        setLoading(false)
      }
    }
    fetchPolicies()
  }, [onPolicyChange])

  useEffect(() => {
    const fetchDetails = async () => {
      if (!selectedPolicy) return
      try {
        const response = await axios.get(`/api/settings/policies/${selectedPolicy}`)
        setPolicyDetails(response.data)
      } catch (error) {
        console.error('Errore nel caricamento dei dettagli:', error)
      }
    }
    fetchDetails()
  }, [selectedPolicy])

  if (loading) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6 animate-pulse">
        <div className="h-4 bg-slate-300 dark:bg-slate-600 rounded w-24 mb-4"></div>
      </div>
    )
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6 space-y-4">
      <div>
        <label className="block text-sm font-semibold mb-2">Profilo di Pseudonimizzazione</label>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
          {policies.map((policy) => (
            <button
              key={policy}
              onClick={() => onPolicyChange(policy)}
              className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                selectedPolicy === policy
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-900 dark:text-white hover:bg-slate-200 dark:hover:bg-slate-600'
              }`}
            >
              {policy}
            </button>
          ))}
        </div>
      </div>

      {policyDetails && (
        <div className="pt-4 border-t border-slate-200 dark:border-slate-700 space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Descrizione</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
              {policyDetails.description || 'Nessuna descrizione disponibile'}
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              Tipi di Entità Rilevate ({policyDetails.entity_count})
            </h3>
            <div className="flex flex-wrap gap-2 mt-2">
              {policyDetails.enabled_entity_types?.map((type) => (
                <span
                  key={type}
                  className="px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-xs font-medium"
                >
                  {type}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default PolicySelector
