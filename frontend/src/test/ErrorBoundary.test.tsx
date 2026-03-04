/**
 * Tests for components/ErrorBoundary.tsx
 * Covers: normal rendering, error state, reset, reload
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ErrorBoundary from '../components/ErrorBoundary'

interface ThrowingComponentProps {
  shouldThrow: boolean
}

// Component that throws an error when told to
const ThrowingComponent = ({ shouldThrow }: ThrowingComponentProps): React.JSX.Element => {
  if (shouldThrow) {
    throw new Error('Test error message')
  }
  return <div>Normal content</div>
}

// Suppress console.error for error boundary tests
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

describe('ErrorBoundary', () => {
  it('renders children when no error occurs', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('renders error UI when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Si è verificato un errore imprevisto')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /riprova/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /ricarica pagina/i })).toBeInTheDocument()
  })

  it('shows error message in details section', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Test error message')).toBeInTheDocument()
  })

  it('Riprova button is present and enabled in error state', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    )
    expect(screen.getByText('Si è verificato un errore imprevisto')).toBeInTheDocument()
    const riprovaBtn = screen.getByRole('button', { name: /riprova/i })
    expect(riprovaBtn).toBeInTheDocument()
    expect(riprovaBtn).not.toBeDisabled()
    // Clicking does not throw
    fireEvent.click(riprovaBtn)
  })

  it('calls window.location.reload when Ricarica pagina is clicked', () => {
    const reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
      configurable: true,
    })
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>,
    )
    fireEvent.click(screen.getByRole('button', { name: /ricarica pagina/i }))
    expect(reloadMock).toHaveBeenCalledOnce()
  })

  it('does not show error UI for non-throwing children', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={false} />
      </ErrorBoundary>,
    )
    expect(screen.queryByText('Si è verificato un errore imprevisto')).not.toBeInTheDocument()
    expect(screen.getByText('Normal content')).toBeInTheDocument()
  })
})
