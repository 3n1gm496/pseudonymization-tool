/**
 * UserManagement component — Admin-only panel for managing local user accounts.
 *
 * Features:
 * - List all users with role badges
 * - Create new users (admin or operator)
 * - Change user roles
 * - Reset user passwords
 * - Delete users (with protection for the last admin)
 */

import React, { useCallback, useEffect, useState } from 'react'
import { User, UserRole } from '../types'
import axios from '../utils/axios'
import { useToast } from '../hooks/useToast'

interface UserManagementProps {
  currentUsername: string
}

interface CreateUserForm {
  username: string
  password: string
  role: UserRole
}

interface PasswordForm {
  newPassword: string
  confirm: string
}

const EMPTY_CREATE_FORM: CreateUserForm = {
  username: '',
  password: '',
  role: 'operator',
}

const EMPTY_PASSWORD_FORM: PasswordForm = {
  newPassword: '',
  confirm: '',
}

const UserManagement: React.FC<UserManagementProps> = ({ currentUsername }) => {
  const { showToast } = useToast()
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [createForm, setCreateForm] = useState<CreateUserForm>(EMPTY_CREATE_FORM)
  const [createLoading, setCreateLoading] = useState(false)
  const [passwordTarget, setPasswordTarget] = useState<string | null>(null)
  const [passwordForm, setPasswordForm] = useState<PasswordForm>(EMPTY_PASSWORD_FORM)
  const [passwordLoading, setPasswordLoading] = useState(false)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await axios.get<{ users: User[]; total: number }>('/api/users')
      setUsers(res.data.users)
    } catch {
      showToast('Errore nel caricamento degli utenti', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    void fetchUsers()
  }, [fetchUsers])

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!createForm.username.trim() || !createForm.password) return
    setCreateLoading(true)
    try {
      await axios.post('/api/users', {
        username: createForm.username.trim().toLowerCase(),
        password: createForm.password,
        role: createForm.role,
      })
      showToast(`Utente '${createForm.username}' creato con successo`, 'success')
      setCreateForm(EMPTY_CREATE_FORM)
      setShowCreateForm(false)
      void fetchUsers()
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Errore nella creazione dell'utente"
      showToast(msg, 'error')
    } finally {
      setCreateLoading(false)
    }
  }

  const handleRoleChange = async (username: string, newRole: UserRole) => {
    try {
      await axios.put(`/api/users/${username}/role`, { role: newRole })
      showToast(`Ruolo di '${username}' aggiornato a '${newRole}'`, 'success')
      void fetchUsers()
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Errore nell'aggiornamento del ruolo"
      showToast(msg, 'error')
    }
  }

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!passwordTarget) return
    if (passwordForm.newPassword !== passwordForm.confirm) {
      showToast('Le password non coincidono', 'error')
      return
    }
    if (passwordForm.newPassword.length < 8) {
      showToast('La password deve essere di almeno 8 caratteri', 'error')
      return
    }
    setPasswordLoading(true)
    try {
      await axios.put(`/api/users/${passwordTarget}/password`, {
        new_password: passwordForm.newPassword,
      })
      showToast(`Password di '${passwordTarget}' aggiornata`, 'success')
      setPasswordTarget(null)
      setPasswordForm(EMPTY_PASSWORD_FORM)
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Errore nell'aggiornamento della password"
      showToast(msg, 'error')
    } finally {
      setPasswordLoading(false)
    }
  }

  const handleDeleteUser = async (username: string) => {
    if (!window.confirm(`Eliminare l'utente '${username}'? Questa azione non è reversibile.`)) {
      return
    }
    try {
      await axios.delete(`/api/users/${username}`)
      showToast(`Utente '${username}' eliminato`, 'success')
      void fetchUsers()
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Errore nell'eliminazione dell'utente"
      showToast(msg, 'error')
    }
  }

  const roleBadge = (role: UserRole) => (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        role === 'admin'
          ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
          : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
      }`}
    >
      {role === 'admin' ? '★ Admin' : 'Operator'}
    </span>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Gestione Utenti
          </h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Gestisci gli account locali. Solo gli amministratori possono accedere a questa sezione.
          </p>
        </div>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          {showCreateForm ? 'Annulla' : '+ Nuovo utente'}
        </button>
      </div>

      {/* Create user form */}
      {showCreateForm && (
        <form
          onSubmit={(e) => { void handleCreateUser(e) }}
          className="p-4 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 space-y-4"
        >
          <h4 className="font-medium text-gray-900 dark:text-white">Crea nuovo utente</h4>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Username
              </label>
              <input
                type="text"
                value={createForm.username}
                onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
                placeholder="es. mario.rossi"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                required
                minLength={1}
                maxLength={64}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Password
              </label>
              <input
                type="password"
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                placeholder="Minimo 8 caratteri"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                required
                minLength={8}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Ruolo
              </label>
              <select
                value={createForm.role}
                onChange={(e) =>
                  setCreateForm({ ...createForm, role: e.target.value as UserRole })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="operator">Operator</option>
                <option value="admin">Admin</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setShowCreateForm(false)
                setCreateForm(EMPTY_CREATE_FORM)
              }}
              className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
            >
              Annulla
            </button>
            <button
              type="submit"
              disabled={createLoading}
              className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {createLoading ? 'Creazione...' : 'Crea utente'}
            </button>
          </div>
        </form>
      )}

      {/* Password reset modal */}
      {passwordTarget && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl p-6 w-full max-w-md mx-4">
            <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Reimposta password — {passwordTarget}
            </h4>
            <form onSubmit={(e) => { void handlePasswordReset(e) }} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Nuova password
                </label>
                <input
                  type="password"
                  value={passwordForm.newPassword}
                  onChange={(e) =>
                    setPasswordForm({ ...passwordForm, newPassword: e.target.value })
                  }
                  placeholder="Minimo 8 caratteri"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                  required
                  minLength={8}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Conferma password
                </label>
                <input
                  type="password"
                  value={passwordForm.confirm}
                  onChange={(e) =>
                    setPasswordForm({ ...passwordForm, confirm: e.target.value })
                  }
                  placeholder="Ripeti la password"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                  required
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => {
                    setPasswordTarget(null)
                    setPasswordForm(EMPTY_PASSWORD_FORM)
                  }}
                  className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                >
                  Annulla
                </button>
                <button
                  type="submit"
                  disabled={passwordLoading}
                  className="px-4 py-2 bg-orange-600 text-white text-sm font-medium rounded-lg hover:bg-orange-700 disabled:opacity-50 transition-colors"
                >
                  {passwordLoading ? 'Aggiornamento...' : 'Aggiorna password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Users table */}
      {loading ? (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
          <span className="ml-2 text-sm text-gray-500">Caricamento utenti...</span>
        </div>
      ) : users.length === 0 ? (
        <p className="text-center text-gray-500 dark:text-gray-400 py-8">
          Nessun utente trovato.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="text-left py-3 px-4 font-medium text-gray-600 dark:text-gray-400">
                  Username
                </th>
                <th className="text-left py-3 px-4 font-medium text-gray-600 dark:text-gray-400">
                  Ruolo
                </th>
                <th className="text-left py-3 px-4 font-medium text-gray-600 dark:text-gray-400">
                  Creato il
                </th>
                <th className="text-left py-3 px-4 font-medium text-gray-600 dark:text-gray-400">
                  Stato
                </th>
                <th className="text-right py-3 px-4 font-medium text-gray-600 dark:text-gray-400">
                  Azioni
                </th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr
                  key={user.username}
                  className="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50"
                >
                  <td className="py-3 px-4">
                    <span className="font-medium text-gray-900 dark:text-white">
                      {user.username}
                    </span>
                    {user.username === currentUsername && (
                      <span className="ml-2 text-xs text-gray-400">(tu)</span>
                    )}
                  </td>
                  <td className="py-3 px-4">{roleBadge(user.role)}</td>
                  <td className="py-3 px-4 text-gray-500 dark:text-gray-400">
                    {new Date(user.created_at).toLocaleDateString('it-IT')}
                  </td>
                  <td className="py-3 px-4">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                        user.is_active
                          ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                          : 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200'
                      }`}
                    >
                      {user.is_active ? 'Attivo' : 'Disabilitato'}
                    </span>
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center justify-end gap-2">
                      {/* Role toggle */}
                      <button
                        onClick={() =>
                          void handleRoleChange(
                            user.username,
                            user.role === 'admin' ? 'operator' : 'admin'
                          )
                        }
                        disabled={user.username === currentUsername}
                        title={
                          user.username === currentUsername
                            ? 'Non puoi modificare il tuo ruolo'
                            : `Cambia a ${user.role === 'admin' ? 'operator' : 'admin'}`
                        }
                        className="px-2 py-1 text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      >
                        {user.role === 'admin' ? '↓ Operator' : '↑ Admin'}
                      </button>

                      {/* Password reset */}
                      <button
                        onClick={() => setPasswordTarget(user.username)}
                        title="Reimposta password"
                        className="px-2 py-1 text-xs text-orange-600 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-900/20 rounded transition-colors"
                      >
                        Password
                      </button>

                      {/* Delete */}
                      <button
                        onClick={() => void handleDeleteUser(user.username)}
                        disabled={user.username === currentUsername}
                        title={
                          user.username === currentUsername
                            ? 'Non puoi eliminare te stesso'
                            : `Elimina ${user.username}`
                        }
                        className="px-2 py-1 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                      >
                        Elimina
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-gray-400 dark:text-gray-500">
        <strong>Admin:</strong> accesso completo (scan, apply, download, impostazioni, gestione utenti).{' '}
        <strong>Operator:</strong> accesso limitato (scan, review, apply, download).
      </p>
    </div>
  )
}

export default UserManagement
