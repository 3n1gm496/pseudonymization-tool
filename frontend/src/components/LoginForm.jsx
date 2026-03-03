import { useState } from 'react'

const LoginForm = ({ onLogin, isLoading }) => {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')

  const handleSubmit = async (event) => {
    event.preventDefault()
    await onLogin(username, password)
  }

  return (
    <div className="max-w-md mx-auto bg-white dark:bg-slate-800 rounded-xl shadow-lg p-8">
      <h2 className="text-2xl font-semibold mb-2">Accesso</h2>
      <p className="text-sm text-slate-600 dark:text-slate-400 mb-6">
        Autenticati per usare lo strumento di pseudonimizzazione.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Username</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
            autoComplete="username"
            required
            disabled={isLoading}
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700"
            autoComplete="current-password"
            required
            disabled={isLoading}
          />
        </div>

        <button
          type="submit"
          disabled={isLoading || !username || !password}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium disabled:opacity-50"
        >
          {isLoading ? 'Accesso in corso...' : 'Login'}
        </button>
      </form>
    </div>
  )
}

export default LoginForm
