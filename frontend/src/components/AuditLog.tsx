import { useState, useEffect, useCallback, type JSX, type KeyboardEvent, type ChangeEvent } from 'react'
import axios from 'axios'
import type { AuditEvent } from '../types'

const PAGE_SIZE = 50

const ACTION_LABELS: Record<string, string> = {
  auth_login: 'Login',
  auth_login_failed: 'Login fallito',
  auth_logout: 'Logout',
  auth_logout_all: 'Logout globale',
  console_scan: 'Scansione console',
  console_apply: 'Apply console',
  batch_create: 'Batch creato',
  batch_scan: 'Batch scansionato',
  batch_apply: 'Batch applicato',
  batch_delete: 'Batch eliminato',
  batch_download: 'Batch scaricato',
  settings_update: 'Impostazioni aggiornate',
  revert_apply: 'Revert applicato',
}

const ACTION_COLORS: Record<string, string> = {
  auth_login_failed: 'text-red-600 dark:text-red-400',
  auth_logout_all: 'text-orange-600 dark:text-orange-400',
  batch_delete: 'text-red-500 dark:text-red-400',
  auth_login: 'text-green-600 dark:text-green-400',
  batch_apply: 'text-blue-600 dark:text-blue-400',
  console_apply: 'text-blue-600 dark:text-blue-400',
}

function formatTimestamp(ts: string | null | undefined): string {
  if (!ts) return '—'
  try {
    return new Date(ts).toLocaleString('it-IT', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ts
  }
}

interface ActionBadgeProps {
  action: string
}

function ActionBadge({ action }: ActionBadgeProps): JSX.Element {
  const label = ACTION_LABELS[action] ?? action
  const color = ACTION_COLORS[action] ?? 'text-slate-700 dark:text-slate-300'
  return <span className={`font-mono text-xs ${color}`}>{label}</span>
}

interface AuditStats {
  total_events: number
  recent_failures?: unknown[]
}

interface StatsBarProps {
  stats: AuditStats | null
}

function StatsBar({ stats }: StatsBarProps): JSX.Element | null {
  if (!stats) return null
  return (
    <div className="grid grid-cols-2 gap-3 mb-4">
      <div className="bg-slate-50 dark:bg-slate-700/50 rounded-lg p-3 text-center">
        <div className="text-2xl font-bold text-slate-800 dark:text-slate-100">{stats.total_events}</div>
        <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Totale eventi</div>
      </div>
      <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-3 text-center">
        <div className="text-2xl font-bold text-red-600 dark:text-red-400">
          {stats.recent_failures?.length ?? 0}
        </div>
        <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">Fallimenti recenti</div>
      </div>
    </div>
  )
}

const AuditLog = (): JSX.Element => {
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<AuditStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [actionFilter, setActionFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')

  const fetchEvents = useCallback(async (): Promise<void> => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      })
      if (actionFilter) params.append('action', actionFilter)
      if (userFilter) params.append('user', userFilter)
      const res = await axios.get<{ events: AuditEvent[]; total: number }>(
        `/api/audit/events?${params.toString()}`,
      )
      setEvents(res.data.events ?? [])
      setTotal(res.data.total ?? 0)
    } catch (err: unknown) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      setError(axiosError.response?.data?.detail ?? 'Errore nel caricamento degli eventi')
    } finally {
      setLoading(false)
    }
  }, [page, actionFilter, userFilter])

  const fetchStats = useCallback(async (): Promise<void> => {
    try {
      const res = await axios.get<AuditStats>('/api/audit/stats')
      setStats(res.data)
    } catch {
      // Stats are non-critical, fail silently
    }
  }, [])

  useEffect(() => {
    void fetchEvents()
    void fetchStats()
  }, [fetchEvents, fetchStats])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const handleFilterChange = (): void => {
    setPage(0)
    void fetchEvents()
  }

  return (
    <div className="space-y-4">
      <StatsBar stats={stats} />
      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <input
          type="text"
          placeholder="Filtra per azione (es. auth_)"
          value={actionFilter}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setActionFilter(e.target.value)}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && handleFilterChange()}
          className="flex-1 min-w-[160px] px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200 placeholder-slate-400"
        />
        <input
          type="text"
          placeholder="Filtra per utente"
          value={userFilter}
          onChange={(e: ChangeEvent<HTMLInputElement>) => setUserFilter(e.target.value)}
          onKeyDown={(e: KeyboardEvent<HTMLInputElement>) => e.key === 'Enter' && handleFilterChange()}
          className="flex-1 min-w-[120px] px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-800 dark:text-slate-200 placeholder-slate-400"
        />
        <button
          onClick={handleFilterChange}
          className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
        >
          Cerca
        </button>
        <button
          onClick={() => {
            setActionFilter('')
            setUserFilter('')
            setPage(0)
          }}
          className="px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
        >
          Reset
        </button>
      </div>
      {/* Table */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg p-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}
      {loading ? (
        <div className="text-center py-8 text-slate-400 text-sm">Caricamento...</div>
      ) : events.length === 0 ? (
        <div className="text-center py-8 text-slate-400 text-sm">Nessun evento trovato.</div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="w-full text-xs">
            <thead className="bg-slate-50 dark:bg-slate-700/50">
              <tr>
                <th className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400 whitespace-nowrap">
                  Data/Ora
                </th>
                <th className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400">
                  Azione
                </th>
                <th className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400">
                  Utente
                </th>
                <th className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400">
                  IP
                </th>
                <th className="px-3 py-2 text-left font-semibold text-slate-600 dark:text-slate-400">
                  Dettagli
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
              {events.map((ev) => (
                <tr
                  key={ev.id}
                  className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors"
                >
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400 whitespace-nowrap font-mono">
                    {formatTimestamp(ev.timestamp)}
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <ActionBadge action={ev.action} />
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300 font-mono">
                    {ev.user ?? '—'}
                  </td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400 font-mono">
                    {ev.ip ?? '—'}
                  </td>
                  <td
                    className="px-3 py-2 text-slate-500 dark:text-slate-400 max-w-[200px] truncate"
                    title={JSON.stringify(ev.details)}
                  >
                    {ev.details && Object.keys(ev.details).length > 0
                      ? Object.entries(ev.details)
                          .slice(0, 3)
                          .map(([k, v]) => `${k}: ${String(v)}`)
                          .join(' · ')
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>{total} eventi totali</span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              ‹
            </button>
            <span className="px-2 py-1">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-2 py-1 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-40 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              ›
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default AuditLog
