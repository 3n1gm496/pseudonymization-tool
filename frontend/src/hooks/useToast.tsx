import { useState, type JSX } from 'react'
import type { Toast, ToastType } from '../types'

interface ToastProps {
  message: string
  type?: ToastType
  onClose: () => void
}

const ToastItem = ({ message, type = 'info', onClose }: ToastProps): JSX.Element => {
  const bgColor: Record<ToastType, string> = {
    success: 'bg-green-500',
    error: 'bg-red-500',
    warning: 'bg-yellow-500',
    info: 'bg-blue-500',
  }

  return (
    <div
      className={`${bgColor[type]} text-white px-4 py-3 rounded-lg shadow-lg animate-slideUp`}
      role="alert"
    >
      <p className="text-sm font-medium">{message}</p>
      <button
        onClick={onClose}
        className="absolute top-2 right-2 text-white hover:text-gray-200"
        aria-label="Close toast"
      >
        ✕
      </button>
    </div>
  )
}

export interface UseToastReturn {
  showToast: (message: string, type?: ToastType, duration?: number) => number
  removeToast: (id: number) => void
  ToastContainer: () => JSX.Element
}

export const useToast = (): UseToastReturn => {
  const [toasts, setToasts] = useState<Toast[]>([])

  const removeToast = (id: number): void => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }

  const showToast = (message: string, type: ToastType = 'info', duration = 3000): number => {
    const id = Date.now()
    setToasts((prev) => [...prev, { id, message, type }])
    if (duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, duration)
    }
    return id
  }

  const ToastContainer = (): JSX.Element => (
    <div className="fixed bottom-4 right-4 space-y-2 z-50">
      {toasts.map((toast) => (
        <ToastItem
          key={toast.id}
          message={toast.message}
          type={toast.type}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>
  )

  return { showToast, removeToast, ToastContainer }
}
