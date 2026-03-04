import type { JSX } from 'react'
import { useTheme } from '../context/ThemeContext'
import type { UserRole } from '../types'

interface HeaderProps {
  user: string | null
  userRole?: UserRole | null
  onLogout: (() => void) | null
  onSettingsClick?: (() => void) | null
}

const Header = ({ user, userRole, onLogout, onSettingsClick }: HeaderProps): JSX.Element => {
  const { isDark, toggleTheme } = useTheme()

  return (
    <header className="bg-gradient-to-r from-blue-600 to-blue-700 dark:from-blue-900 dark:to-blue-950 text-white shadow-lg">
      <div className="w-full px-4 py-6 flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold">Pseudonymization Tool</h1>
          <p className="text-blue-100 dark:text-blue-300 text-sm mt-1">Privacy by Design</p>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-blue-100">{user}</span>
              {userRole && (
                <span
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                    userRole === 'admin'
                      ? 'bg-purple-500/30 text-purple-100 border border-purple-400/40'
                      : 'bg-blue-500/30 text-blue-100 border border-blue-400/40'
                  }`}
                  title={
                    userRole === 'admin'
                      ? 'Amministratore: accesso completo'
                      : 'Operatore: accesso limitato'
                  }
                >
                  {userRole === 'admin' ? '★ Admin' : 'Operator'}
                </span>
              )}
            </div>
          )}
          {onSettingsClick && (
            <button
              onClick={onSettingsClick}
              className="px-3 py-2 bg-white/20 hover:bg-white/30 rounded-lg transition-colors text-sm"
              aria-label="Settings"
              title="Impostazioni (LDAP, etc)"
            >
              ⚙️
            </button>
          )}
          {user && onLogout && (
            <button
              onClick={onLogout}
              className="px-3 py-2 bg-white/20 hover:bg-white/30 rounded-lg transition-colors text-sm"
              aria-label="Logout"
            >
              Logout
            </button>
          )}
          <button
            onClick={toggleTheme}
            className="px-4 py-2 bg-white/20 hover:bg-white/30 rounded-lg transition-colors flex items-center gap-2"
            aria-label="Toggle theme"
          >
            {isDark ? '☀️ Light' : '🌙 Dark'}
          </button>
        </div>
      </div>
    </header>
  )
}

export default Header
