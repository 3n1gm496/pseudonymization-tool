/**
 * Tests for hooks/useToast.jsx
 * Covers: showToast, removeToast, ToastContainer rendering, auto-dismiss
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { renderHook } from '@testing-library/react'
import { useToast } from '../hooks/useToast'

describe('useToast hook', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('starts with no toasts', () => {
    const { result } = renderHook(() => useToast())
    const { ToastContainer } = result.current
    render(<ToastContainer />)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('showToast adds a toast to the container', () => {
    const { result } = renderHook(() => useToast())
    const { ToastContainer } = result.current

    const { rerender } = render(<ToastContainer />)

    act(() => {
      result.current.showToast('Hello world', 'info', 0)
    })

    rerender(<result.current.ToastContainer />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('showToast returns a numeric id', () => {
    const { result } = renderHook(() => useToast())
    let id
    act(() => {
      id = result.current.showToast('Test', 'info', 0)
    })
    expect(typeof id).toBe('number')
  })

  it('removeToast removes a specific toast', () => {
    const { result } = renderHook(() => useToast())
    let id

    act(() => {
      id = result.current.showToast('Removable toast', 'info', 0)
    })

    const { rerender } = render(<result.current.ToastContainer />)
    expect(screen.getByText('Removable toast')).toBeInTheDocument()

    act(() => {
      result.current.removeToast(id)
    })

    rerender(<result.current.ToastContainer />)
    expect(screen.queryByText('Removable toast')).not.toBeInTheDocument()
  })

  it('toast auto-dismisses after duration', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.showToast('Auto dismiss', 'info', 1000)
    })

    const { rerender } = render(<result.current.ToastContainer />)
    expect(screen.getByText('Auto dismiss')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(1001)
    })

    rerender(<result.current.ToastContainer />)
    expect(screen.queryByText('Auto dismiss')).not.toBeInTheDocument()
  })

  it('toast with duration=0 does not auto-dismiss', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.showToast('Persistent toast', 'info', 0)
    })

    const { rerender } = render(<result.current.ToastContainer />)

    act(() => {
      vi.advanceTimersByTime(10000)
    })

    rerender(<result.current.ToastContainer />)
    expect(screen.getByText('Persistent toast')).toBeInTheDocument()
  })

  it('clicking close button removes the toast', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.showToast('Closeable toast', 'info', 0)
    })

    const { rerender } = render(<result.current.ToastContainer />)
    expect(screen.getByText('Closeable toast')).toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Close toast'))

    rerender(<result.current.ToastContainer />)
    expect(screen.queryByText('Closeable toast')).not.toBeInTheDocument()
  })

  it('multiple toasts can coexist', () => {
    const { result } = renderHook(() => useToast())

    act(() => {
      result.current.showToast('Toast 1', 'info', 0)
      result.current.showToast('Toast 2', 'success', 0)
      result.current.showToast('Toast 3', 'error', 0)
    })

    render(<result.current.ToastContainer />)
    expect(screen.getByText('Toast 1')).toBeInTheDocument()
    expect(screen.getByText('Toast 2')).toBeInTheDocument()
    expect(screen.getByText('Toast 3')).toBeInTheDocument()
  })
})
