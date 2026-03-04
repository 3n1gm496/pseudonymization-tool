import { useState, type JSX } from 'react'
import AuditLog from './AuditLog'
import LDAPSettings from './LDAPSettings'
import type { ToastType } from '../types'

interface SettingsPanelProps {
  isOpen: boolean
  onClose: () => void
  showToast: (message: string, type?: ToastType) => void
}

type TabId = 'ldap' | 'audit' | 'info'

const SettingsPanel = ({ isOpen, onClose, showToast }: SettingsPanelProps): JSX.Element | null => {
  const [activeTab, setActiveTab] = useState<TabId>('ldap')

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 p-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">⚙️ Impostazioni</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-2xl leading-none"
            aria-label="Chiudi"
          >
            ✕
          </button>
        </div>
        {/* Tabs */}
        <div className="flex border-b border-slate-200 dark:border-slate-700">
          {(['ldap', 'audit', 'info'] as TabId[]).map((tab) => {
            const labels: Record<TabId, string> = {
              ldap: '🔗 LDAP',
              audit: '📋 Audit Log',
              info: 'ℹ️ Info',
            }
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 px-4 py-3 font-medium text-sm transition-colors ${
                  activeTab === tab
                    ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {labels[tab]}
              </button>
            )
          })}
        </div>
        {/* Content */}
        <div className="p-6">
          {activeTab === 'ldap' && <LDAPSettings showToast={showToast} />}
          {activeTab === 'audit' && <AuditLog />}
          {activeTab === 'info' && (
            <div className="space-y-4">
              <div>
                <h3 className="font-semibold mb-2">Local Pseudonymization Tool</h3>
                <p className="text-sm text-slate-600 dark:text-slate-400 mb-3">
                  Tool per pseudoanonimizzare dati sensibili prima di inviarli a servizi online (es.
                  AI).
                </p>
              </div>
              <div>
                <h4 className="font-semibold mb-2 text-sm">Flussi disponibili</h4>
                <ul className="text-sm space-y-1 text-slate-700 dark:text-slate-300">
                  <li>
                    📝 <b>Pseudonimizza:</b> Scansiona → Rivedi → Apply → Scarica testo + mapping
                  </li>
                  <li>
                    📦 <b>Prepara per AI:</b> Esporta testo pseudonimizzato + mapping.enc per
                    inviare all&apos;AI
                  </li>
                  <li>
                    🔓 <b>Decifra AI:</b> Decifra la risposta pseudonimizzata dell&apos;AI con lo
                    stesso mapping
                  </li>
                  <li>🔄 <b>Revert ZIP:</b> Reverta file ZIP completi del tool</li>
                </ul>
              </div>
              <div>
                <h4 className="font-semibold mb-2 text-sm">Detettori disponibili</h4>
                <ul className="text-sm space-y-1 text-slate-700 dark:text-slate-300">
                  <li>🔤 Email, Indirizzi IP, URL, Numeri telefonici</li>
                  <li>🏛️ Codice Fiscale, Partita IVA</li>
                  <li>🔗 Utenti LDAP (se configurato)</li>
                  <li>📚 Dizionario personalizzato (hostname, person names, project codes)</li>
                </ul>
              </div>
              <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700 rounded-lg p-3">
                <p className="text-xs text-blue-800 dark:text-blue-200">
                  <b>Data:</b> 4 marzo 2026
                  <br />
                  <b>Version:</b> 5.0.0
                  <br />
                  <b>Security:</b> AES-256-GCM, PBKDF2, Session auth, Rate limiting, Audit log
                  SQLite
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default SettingsPanel
