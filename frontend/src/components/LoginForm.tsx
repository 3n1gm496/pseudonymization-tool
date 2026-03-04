import { useState, useEffect, type JSX, type FormEvent, type ChangeEvent } from 'react'
import axios from '../utils/axios'

interface LoginFormProps {
  onLogin: (username: string, password: string, authMethod: 'local' | 'ldap') => Promise<void>
  isLoading: boolean
}

const LoginForm = ({ onLogin, isLoading }: LoginFormProps): JSX.Element => {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [authMethod, setAuthMethod] = useState<'local' | 'ldap'>('local')
  const [ldapAvailable, setLdapAvailable] = useState(false)

  useEffect(() => {
    // Verifica se l'autenticazione LDAP è disponibile e configurata
    axios
      .get<{ ldap_auth_available: boolean }>('/api/auth/ldap-status')
      .then((res) => {
        setLdapAvailable(res.data.ldap_auth_available ?? false)
      })
      .catch(() => {
        setLdapAvailable(false)
      })
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    await onLogin(username, password, authMethod)
  }

  return (
    <div className="max-w-md mx-auto bg-white dark:bg-slate-800 rounded-xl shadow-lg p-8">
      <h2 className="text-2xl font-semibold mb-2">Accesso</h2>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Autenticati per usare lo strumento di pseudonimizzazione.
      </p>

      {/* Selezione metodo di autenticazione — visibile solo se LDAP è configurato */}
      {ldapAvailable && (
        <div className="mb-5">
          <label className="block text-sm font-medium mb-2">Metodo di accesso</label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setAuthMethod('local')
                setUsername('admin')
              }}
              className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                authMethod === 'local'
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600 hover:border-blue-400'
              }`}
            >
              🔒 Locale
            </button>
            <button
              type="button"
              onClick={() => {
                setAuthMethod('ldap')
                setUsername('')
              }}
              className={`flex-1 px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${
                authMethod === 'ldap'
                  ? 'bg-indigo-600 text-white border-indigo-600'
                  : 'bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 border-slate-300 dark:border-slate-600 hover:border-indigo-400'
              }`}
            >
              🏢 Aziendale (LDAP)
            </button>
          </div>
          {authMethod === 'ldap' && (
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
              Usa le tue credenziali aziendali. Il nome utente corrisponde all&apos;attributo{' '}
              <code className="bg-slate-100 dark:bg-slate-700 px-1 rounded">cn</code> del tuo account.
            </p>
          )}
        </div>
      )}

      <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">
            {authMethod === 'ldap' ? 'Nome utente aziendale (cn)' : 'Username'}
          </label>
          <input
            type="text"
            value={username}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
            autoComplete="username"
            placeholder={authMethod === 'ldap' ? 'es: mario.rossi' : 'admin'}
            required
            disabled={isLoading}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
            autoComplete="current-password"
            required
            disabled={isLoading}
          />
        </div>
        <button
          type="submit"
          disabled={isLoading || !username || !password}
          className={`w-full px-4 py-2 text-white rounded-lg font-medium disabled:opacity-50 ${
            authMethod === 'ldap'
              ? 'bg-indigo-600 hover:bg-indigo-700'
              : 'bg-blue-600 hover:bg-blue-700'
          }`}
        >
          {isLoading ? 'Accesso in corso...' : authMethod === 'ldap' ? 'Accedi con LDAP' : 'Login'}
        </button>
      </form>
    </div>
  )
}

export default LoginForm
