/**
 * Tests for components/Header.jsx
 * Covers: rendering, logout button, settings button, theme toggle
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Header from '../components/Header'
import { ThemeProvider } from '../context/ThemeContext'

// Helper to render with ThemeProvider
const renderWithTheme = (ui) => {
  return render(<ThemeProvider>{ui}</ThemeProvider>)
}

describe('Header', () => {
  it('renders the app title', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    expect(screen.getByText('Pseudonymization Tool')).toBeInTheDocument()
  })

  it('renders the subtitle', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    expect(screen.getByText('Privacy by Design')).toBeInTheDocument()
  })

  it('shows username when user prop is provided', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('does not show username when user prop is null', () => {
    renderWithTheme(<Header user={null} onLogout={vi.fn()} />)
    expect(screen.queryByText('admin')).not.toBeInTheDocument()
  })

  it('shows logout button when user and onLogout are provided', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    expect(screen.getByRole('button', { name: /logout/i })).toBeInTheDocument()
  })

  it('does not show logout button when user is null', () => {
    renderWithTheme(<Header user={null} onLogout={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /logout/i })).not.toBeInTheDocument()
  })

  it('calls onLogout when logout button is clicked', () => {
    const onLogout = vi.fn()
    renderWithTheme(<Header user="admin" onLogout={onLogout} />)
    fireEvent.click(screen.getByRole('button', { name: /logout/i }))
    expect(onLogout).toHaveBeenCalledOnce()
  })

  it('shows settings button when onSettingsClick is provided', () => {
    renderWithTheme(
      <Header user="admin" onLogout={vi.fn()} onSettingsClick={vi.fn()} />
    )
    expect(screen.getByRole('button', { name: /settings/i })).toBeInTheDocument()
  })

  it('does not show settings button when onSettingsClick is not provided', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /settings/i })).not.toBeInTheDocument()
  })

  it('calls onSettingsClick when settings button is clicked', () => {
    const onSettingsClick = vi.fn()
    renderWithTheme(
      <Header user="admin" onLogout={vi.fn()} onSettingsClick={onSettingsClick} />
    )
    fireEvent.click(screen.getByRole('button', { name: /settings/i }))
    expect(onSettingsClick).toHaveBeenCalledOnce()
  })

  it('renders theme toggle button', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    expect(screen.getByRole('button', { name: /toggle theme/i })).toBeInTheDocument()
  })

  it('toggles theme when toggle button is clicked', () => {
    renderWithTheme(<Header user="admin" onLogout={vi.fn()} />)
    const toggleBtn = screen.getByRole('button', { name: /toggle theme/i })
    // Initial state: light mode (jsdom default)
    expect(toggleBtn).toHaveTextContent(/dark/i)
    fireEvent.click(toggleBtn)
    expect(toggleBtn).toHaveTextContent(/light/i)
  })
})
