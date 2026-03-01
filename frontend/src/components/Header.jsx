import React from 'react'
import { useTheme } from '../context/ThemeContext'

const Header = ({ user, onLogout, onSettingsClick }) => {
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
            <span className="text-sm text-blue-100">{user}</span>
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
