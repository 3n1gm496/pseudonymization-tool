import { useEffect, useState, type JSX, type FormEvent, type ChangeEvent } from 'react'
import axios from '../utils/axios'
import type { LDAPTestResult, ToastType } from '../types'

interface LDAPSettingsProps {
  showToast: (message: string, type?: ToastType) => void
}

interface LDAPDiagnostics {
  [key: string]: unknown
}

const LDAPSettings = ({ showToast }: LDAPSettingsProps): JSX.Element => {
  const [isLoading, setIsLoading] = useState(false)
  const [isConfigured, setIsConfigured] = useState(false)
  const [testResult, setTestResult] = useState<LDAPTestResult | null>(null)
  const [diagnostics, setDiagnostics] = useState<LDAPDiagnostics | null>(null)
  const [showForm, setShowForm] = useState(false)

  // Form state — Connection
  const [host, setHost] = useState('')
  const [port, setPort] = useState('389')
  const [baseDN, setBaseDN] = useState('')
  const [bindDN, setBindDN] = useState('')
  const [bindPassword, setBindPassword] = useState('')
  const [searchFilter, setSearchFilter] = useState('(uid=*)')
  const [useSSL, setUseSSL] = useState(false)
  const [starttls, setStarttls] = useState(false)
  const [tlsValidateCert, setTlsValidateCert] = useState(false)

  // Form state — Authentication
  const [authEnabled, setAuthEnabled] = useState(false)
  const [authUserBaseDN, setAuthUserBaseDN] = useState('')
  const [authAdminGroupDN, setAuthAdminGroupDN] = useState('')
  const [authOperatorGroupDN, setAuthOperatorGroupDN] = useState('')
  const [authDefaultRole, setAuthDefaultRole] = useState<'admin' | 'operator'>('operator')

  useEffect(() => {
    void loadConfig()
  }, [])

  const loadConfig = async (): Promise<void> => {
    try {
      const response = await axios.get<{
        configured?: boolean
        diagnostics?: LDAPDiagnostics | null
        host?: string
        port?: number | string
        base_dn?: string
        bind_dn?: string
        search_filter?: string
        use_ssl?: boolean
        starttls?: boolean
        tls_validate_cert?: boolean
        auth_enabled?: boolean
        auth_user_base_dn?: string
        auth_admin_group_dn?: string
        auth_operator_group_dn?: string
        auth_default_role?: 'admin' | 'operator'
      }>('/api/settings/ldap')
      setIsConfigured(response.data.configured ?? false)
      setDiagnostics(response.data.diagnostics ?? null)
      if (response.data.host) {
        setHost(response.data.host)
        setPort(String(response.data.port ?? '389'))
        setBaseDN(response.data.base_dn ?? '')
        setBindDN(response.data.bind_dn ?? '')
        setSearchFilter(response.data.search_filter ?? '(uid=*)')
        setUseSSL(response.data.use_ssl ?? false)
        setStarttls(response.data.starttls ?? false)
        setTlsValidateCert(response.data.tls_validate_cert ?? false)
      }
      // Authentication fields
      setAuthEnabled(response.data.auth_enabled ?? false)
      setAuthUserBaseDN(response.data.auth_user_base_dn ?? '')
      setAuthAdminGroupDN(response.data.auth_admin_group_dn ?? '')
      setAuthOperatorGroupDN(response.data.auth_operator_group_dn ?? '')
      setAuthDefaultRole(response.data.auth_default_role ?? 'operator')
    } catch {
      setDiagnostics(null)
    }
  }

  const handleSave = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault()
    if (!host || !baseDN) {
      showToast('Host e BaseDN sono obbligatori', 'error')
      return
    }
    if (authEnabled && !authUserBaseDN) {
      showToast('Auth User Base DN e obbligatorio quando l\'autenticazione LDAP e attiva', 'error')
      return
    }
    setIsLoading(true)
    try {
      await axios.post('/api/settings/ldap', {
        host,
        port: parseInt(port, 10),
        base_dn: baseDN,
        bind_dn: bindDN,
        bind_password: bindPassword,
        search_filter: searchFilter,
        use_ssl: useSSL,
        starttls,
        tls_validate_cert: tlsValidateCert,
        auth_enabled: authEnabled,
        auth_user_base_dn: authUserBaseDN,
        auth_admin_group_dn: authAdminGroupDN,
        auth_operator_group_dn: authOperatorGroupDN,
        auth_default_role: authDefaultRole,
      })
      showToast('Configurazione LDAP salvata', 'success')
      setShowForm(false)
      void loadConfig()
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      showToast(axiosError.response?.data?.detail ?? 'Errore salvataggio LDAP', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleTest = async (): Promise<void> => {
    setIsLoading(true)
    try {
      const response = await axios.post<LDAPTestResult>('/api/settings/ldap/test')
      setTestResult({
        ok: response.data.ok,
        error: response.data.error,
        user_count: response.data.user_count,
      })
      if (response.data.ok) {
        showToast(`Connessione OK - ${response.data.user_count ?? 0} utenti trovati`, 'success')
      } else {
        showToast(response.data.error ?? 'Test fallito', 'error')
      }
    } catch {
      showToast('Errore test connessione', 'error')
    } finally {
      setIsLoading(false)
    }
  }

  const handleRefresh = async (): Promise<void> => {
    setIsLoading(true)
    try {
      const response = await axios.post<{
        ok?: boolean
        message?: string
        diagnostics?: LDAPDiagnostics
      }>('/api/settings/ldap/refresh')
      setDiagnostics(response.data.diagnostics ?? null)
      if (response.data.ok) {
        showToast('Cache LDAP aggiornata', 'success')
      } else {
        showToast(response.data.message ?? 'Refresh completato con warnings', 'warning')
      }
    } catch {
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
              Configurato
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
              <div>
                <span className="font-medium">TLS:</span>{' '}
                {useSSL ? 'SSL' : starttls ? 'STARTTLS' : 'Nessuno'}
                {tlsValidateCert ? ' (certificato validato)' : ''}
              </div>
              <div>
                <span className="font-medium">Autenticazione LDAP:</span>{' '}
                {authEnabled ? (
                  <span className="text-green-600 dark:text-green-400 font-semibold">Attiva</span>
                ) : (
                  <span className="text-slate-500">Disattiva</span>
                )}
              </div>
              {authEnabled && authUserBaseDN && (
                <div>
                  <span className="font-medium">User Base DN:</span> {authUserBaseDN}
                </div>
              )}
            </div>
            <div className="flex gap-3 flex-wrap mb-4">
              <button
                onClick={() => void handleTest()}
                disabled={isLoading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                Test connessione
              </button>
              <button
                onClick={() => void handleRefresh()}
                disabled={isLoading}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                Aggiorna cache
              </button>
              <button
                onClick={() => setShowForm(true)}
                disabled={isLoading}
                className="px-4 py-2 bg-slate-400 hover:bg-slate-500 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                Modifica
              </button>
            </div>
          </>
        )}
        {showForm && (
          <form onSubmit={(e) => void handleSave(e)} className="space-y-4">
            {/* ── Connection Settings ────────────────────────────────────── */}
            <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300 border-b border-slate-200 dark:border-slate-600 pb-1">
              Connessione
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium mb-1">Host LDAP *</label>
                <input
                  type="text"
                  value={host}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setHost(e.target.value)}
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
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setPort(e.target.value)}
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
                onChange={(e: ChangeEvent<HTMLInputElement>) => setBaseDN(e.target.value)}
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
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setBindDN(e.target.value)}
                  placeholder="es: cn=admin,ou=people,dc=ente,dc=it"
                  className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                  disabled={isLoading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1">Password Bind (opzionale)</label>
                <input
                  type="password"
                  value={bindPassword}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setBindPassword(e.target.value)}
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
                onChange={(e: ChangeEvent<HTMLInputElement>) => setSearchFilter(e.target.value)}
                placeholder="(uid=*)"
                className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm font-mono"
                disabled={isLoading}
              />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                Es: (uid=*), (|(uid=*)(cn=*))
              </p>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="useSSL"
                  checked={useSSL}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => {
                    setUseSSL(e.target.checked)
                    if (e.target.checked) setStarttls(false)
                  }}
                  disabled={isLoading}
                  className="rounded"
                />
                <label htmlFor="useSSL" className="text-sm font-medium">SSL</label>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="starttls"
                  checked={starttls}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => {
                    setStarttls(e.target.checked)
                    if (e.target.checked) setUseSSL(false)
                  }}
                  disabled={isLoading}
                  className="rounded"
                />
                <label htmlFor="starttls" className="text-sm font-medium">STARTTLS</label>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="tlsValidateCert"
                  checked={tlsValidateCert}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setTlsValidateCert(e.target.checked)}
                  disabled={isLoading}
                  className="rounded"
                />
                <label htmlFor="tlsValidateCert" className="text-sm font-medium">Valida certificato TLS</label>
              </div>
            </div>

            {/* ── Authentication Settings ────────────────────────────────── */}
            <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300 border-b border-slate-200 dark:border-slate-600 pb-1 mt-6">
              Autenticazione LDAP (eDirectory)
            </h4>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="authEnabled"
                checked={authEnabled}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setAuthEnabled(e.target.checked)}
                disabled={isLoading}
                className="rounded"
              />
              <label htmlFor="authEnabled" className="text-sm font-medium">
                Abilita autenticazione tramite LDAP
              </label>
            </div>
            {authEnabled && (
              <div className="space-y-3 pl-4 border-l-2 border-blue-300 dark:border-blue-700">
                <div>
                  <label className="block text-sm font-medium mb-1">User Base DN *</label>
                  <input
                    type="text"
                    value={authUserBaseDN}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setAuthUserBaseDN(e.target.value)}
                    placeholder="es: ou=users,o=ente"
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                    disabled={isLoading}
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    Base DN per la ricerca utenti. L&apos;autenticazione usa l&apos;attributo cn di inetOrgPerson.
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Admin Group DN (opzionale)</label>
                  <input
                    type="text"
                    value={authAdminGroupDN}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setAuthAdminGroupDN(e.target.value)}
                    placeholder="es: cn=pseudonymizer-admins,ou=groups,o=ente"
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                    disabled={isLoading}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Operator Group DN (opzionale)</label>
                  <input
                    type="text"
                    value={authOperatorGroupDN}
                    onChange={(e: ChangeEvent<HTMLInputElement>) => setAuthOperatorGroupDN(e.target.value)}
                    placeholder="es: cn=pseudonymizer-operators,ou=groups,o=ente"
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                    disabled={isLoading}
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium mb-1">Ruolo di default</label>
                  <select
                    value={authDefaultRole}
                    onChange={(e: ChangeEvent<HTMLSelectElement>) =>
                      setAuthDefaultRole(e.target.value as 'admin' | 'operator')
                    }
                    className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-sm"
                    disabled={isLoading}
                  >
                    <option value="operator">Operator</option>
                    <option value="admin">Admin</option>
                  </select>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    Ruolo assegnato agli utenti LDAP che non appartengono a nessun gruppo configurato.
                  </p>
                </div>
              </div>
            )}

            <div className="flex gap-3 pt-4">
              <button
                type="submit"
                disabled={isLoading}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg disabled:opacity-50 text-sm"
              >
                {isLoading ? 'Salvataggio...' : 'Salva'}
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
              Configura un server LDAP per rilevare automaticamente account utenti durante la
              scansione e per abilitare l&apos;autenticazione aziendale.
            </p>
            <button
              onClick={() => setShowForm(true)}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm"
            >
              Configura LDAP
            </button>
          </div>
        )}
      </div>
      {testResult && (
        <div
          className={`p-4 rounded-lg ${testResult.ok ? 'bg-green-50 dark:bg-green-900/30 border border-green-200' : 'bg-red-50 dark:bg-red-900/30 border border-red-200'}`}
        >
          <h4 className="font-semibold mb-2">Risultato test</h4>
          <p
            className={`text-sm ${testResult.ok ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'}`}
          >
            {testResult.ok
              ? `Connessione riuscita - ${testResult.user_count ?? 0} utenti trovati`
              : `${testResult.error ?? 'Errore sconosciuto'}`}
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
