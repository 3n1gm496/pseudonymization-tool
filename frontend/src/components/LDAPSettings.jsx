import React, { useEffect, useState } from 'react'
import axios from '../utils/axios'

const LDAPSettings = ({ showToast }) => {
  const [isLoading, setIsLoading] = useState(false)
  const [isConfigured, setIsConfigured] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [diagnostics, setDiagnostics] = useState(null)
  const [showForm, setShowForm] = useState(false)

  // Form state
  const [host, setHost] = useState('')
  const [port, setPort] = useState('389')
  const [baseDN, setBaseDN] = useState('')
  const [bindDN, setBindDN] = useState('')
  const [bindPassword, setBindPassword] = useState('')
  const [searchFilter, setSearchFilter] = useState('(uid=*)')
  const [useSSL, setUseSSL] = useState(false)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    try {
      const response = await axios.get('/api/settings/ldap')
      setIsConfigured(response.data.configured || false)
      setDiagnostics(response.data.diagnostics)
      if (response.data.host) {
        setHost(response.data.host)
        setPort(response.data.port || '389')
        setBaseDN(response.data.base_dn || '')
        setBindDN(response.data.bind_dn || '')
        setSearchFilter(response.data.search_filter || '(uid=*)')
        setUseSSL(response.data.use_ssl || false)
      }
    } catch (error) {
      setDiagnostics(null)
    }
  }

  const handleSave = async (e) => {
    e.preventDefault()
    if (!host || !baseDN) {
      showToast('Host e BaseDN sono obbligatori', 'error')
      return
    }

    setIsLoading(true)
    try {
      await axios.post('/api/settings/ldap', {
        host,
        port: parseInt(port),
        base_dn: baseDN,
        bind_dn: bindDN,
        bind_password: bindPassword,
        search_filter: searchFilter,
        use_ssl: useSSL,
      })
      showToast('Configurazione LDAP salvata', 'success')
      setShowForm(false)
      loadConfig()
    } catch (error) {
      showToast(error.response?.data?.detail || 'Errore salvataggio LDAP', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleTest = async () => {
    setIsLoading(true)
    try {
      const response = await axios.post('/api/settings/ldap/test')
      setTestResult({
        ok: response.data.ok,
        error: response.data.error,
        user_count: response.data.user_count,
      })
      if (response.data.ok) {
        showToast(`Connessione OK - ${response.data.user_count} utenti trovati`, 'success')
      } else {
        showToast(response.data.error || 'Test fallito', 'error')
      }
    } catch (error) {
      showToast('Errore test connessione', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRefresh = async () => {
    setIsLoading(true)
    try {
      const response = await axios.post('/api/settings/ldap/refresh')
      setDiagnostics(response.data.diagnostics)
      if (response.data.ok) {
        showToast('Cache LDAP aggiornata', 'success')
      } else {
        showToast(response.data.message || 'Refresh completato con warnings', 'warning')
      }
    } catch (error) {
      showToast('Errore refresh cache', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Integrazione LDAP</h3>
          {isConfigured && (
            <span className="text-xs font-bold bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 px-3 py-1 rounded-full">
              ✓ Configurato
            </span>
          )}
        </div>

        {isConfigured && !showForm && (
          <>
            <div className="mb-4 p-3 rounded bg-slate-50 dark:bg-slate-900 text-sm space-y-1">
              <div>
                <span className="font-medium">Host:</span> {host}:{port}
              </div>
              <div>
                <span className="font-medium">Base DN:</span> {baseDN}
              </div>
              {bindDN && (
                <div>
                  <span className="font-medium">Bind DN:</span> {bindDN}
                </div>
              )}
              <div>
                <span className="font-medium">Filter:</span> {searchFilter}
              </div>
            </div>

            <div className="flex gap-3 flex-wrap mb-4">
              <button
                onClick={handleTest}
                disabled={isLoading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                🔗 Test connessione
              </button>
              <button
                onClick={handleRefresh}
                disabled={isLoading}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                🔄 Aggiorna cache
              </button>
              <button
                onClick={() => setShowForm(true)}
                disabled={isLoading}
                className="px-4 py-2 bg-slate-400 hover:bg-slate-500 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                ⚙️ Modifica
              </button>
            </div>
          </>
        )}

        {showForm && (
          <form onSubmit={handleSave} className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Host LDAP *</label>
                <input
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  placeholder="es: ldap.ente.it"
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                  disabled={isLoading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Port</label>
                <input
                  type="number"
                  value={port}
                  onChange={(e) => setPort(e.target.value)}
                  placeholder="389"
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Base DN *</label>
              <input
                type="text"
                value={baseDN}
                onChange={(e) => setBaseDN(e.target.value)}
                placeholder="es: dc=ente,dc=it"
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                disabled={isLoading}
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Bind DN (opzionale)</label>
                <input
                  type="text"
                  value={bindDN}
                  onChange={(e) => setBindDN(e.target.value)}
                  placeholder="es: uid=admin,ou=people,dc=ente,dc=it"
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                  disabled={isLoading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Password Bind (opzionale)</label>
                <input
                  type="password"
                  value={bindPassword}
                  onChange={(e) => setBindPassword(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                  disabled={isLoading}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Search Filter</label>
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="(uid=*)"
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm font-mono"
                disabled={isLoading}
              />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Es: (uid=*), (|(uid=*)(cn=*))
              </p>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="useSSL"
                checked={useSSL}
                onChange={(e) => setUseSSL(e.target.checked)}
                disabled={isLoading}
                className="rounded"
              />
              <label htmlFor="useSSL" className="text-sm font-medium">
                Usa SSL/TLS
              </label>
            </div>

            <div className="flex gap-3 pt-4">
              <button
                type="submit"
                disabled={isLoading}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                {isLoading ? 'Salvataggio...' : '✓ Salva'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                disabled={isLoading}
                className="px-4 py-2 bg-slate-400 hover:bg-slate-500 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                Annulla
              </button>
            </div>
          </form>
        )}

        {!isConfigured && !showForm && (
          <div>
            <p className="text-sm text-slate-600 dark:text-slate-400 mb-4">
              Configura un server LDAP per rilevare automaticamente account utenti durante la scansione.
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
            >
              ⚙️ Configura LDAP
            </button>
          </div>
        )}
      </div>

      {testResult && (
        <div className={`p-4 rounded-lg ${testResult.ok ? 'bg-green-50 dark:bg-green-900/30 border border-green-200' : 'bg-red-50 dark:bg-red-900/30 border border-red-200'}`}>
          <h4 className="font-semibold mb-2">Risultato test</h4>
          <p className={`text-sm ${testResult.ok ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'}`}>
            {testResult.ok ? `✓ Connessione riuscita - ${testResult.user_count} utenti trovati` : `✗ ${testResult.error}`}
          </p>
        </div>
      )}

      {diagnostics && (
        <div className="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 border border-slate-200 dark:border-slate-700">
          <h4 className="font-semibold mb-2 text-sm">Diagnostica</h4>
          <pre className="text-xs overflow-auto max-h-40 text-slate-700 dark:text-slate-300">
            {JSON.stringify(diagnostics, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

export default LDAPSettings
