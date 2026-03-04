import { useState, type JSX, type ComponentType } from 'react'
import DecipherAIResponse from './DecipherAIResponse'
import RevertBatchZip from './RevertBatchZip'
import type { Batch, ToastType } from '../types'

interface SharedProps {
  batch?: Batch | null
  pseudonymizedText?: string | null
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  showToast: (message: string, type?: ToastType) => void
}

interface TabConfig {
  id: string
  label: string
  component: ComponentType<SharedProps>
  description: string
}

interface RevertPanelProps {
  batch: Batch | null
  pseudonymizedText: string | null
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  showToast: (message: string, type?: ToastType) => void
}

const tabs: TabConfig[] = [
  {
    id: 'decipher',
    label: '🔓 Decifra Risposta AI',
    component: DecipherAIResponse as ComponentType<SharedProps>,
    description: "Decifera la risposta pseudonimizzata dell'AI",
  },
  {
    id: 'zip',
    label: '📦 Revert Batch ZIP',
    component: RevertBatchZip as ComponentType<SharedProps>,
    description: 'Revert completo di archivi ZIP del tool',
  },
]

const RevertPanel = ({
  batch,
  pseudonymizedText,
  isLoading,
  setIsLoading,
  showToast,
}: RevertPanelProps): JSX.Element => {
  const [activeTab, setActiveTab] = useState('decipher')

  const activeTabConfig = tabs.find((t) => t.id === activeTab)
  const ActiveComponent = activeTabConfig?.component

  return (
    <div className="w-full space-y-6">
      {/* TAB HEADER */}
      <div className="flex flex-wrap gap-2 border-b border-slate-200 dark:border-slate-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`pb-3 px-4 font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-b-2 border-blue-600 text-blue-600 dark:text-blue-400'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
            title={tab.description}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {/* TAB CONTENT */}
      {ActiveComponent && (
        <ActiveComponent
          batch={batch}
          pseudonymizedText={pseudonymizedText}
          isLoading={isLoading}
          setIsLoading={setIsLoading}
          showToast={showToast}
        />
      )}
    </div>
  )
}

export default RevertPanel
