/**
 * Tests for components/LoginForm.jsx
 * Covers: rendering, form submission, loading state, disabled state
 *
 * Note: LoginForm uses <label> without htmlFor, so we use
 * getByRole('textbox'), getByDisplayValue, and getAllByRole('textbox')
 * instead of getByLabelText.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoginForm from '../components/LoginForm'

// Helper: get username input (type=text) and password input (type=password)
const getInputs = () => {
  const allInputs = document.querySelectorAll('input')
  const usernameInput = Array.from(allInputs).find((i) => i.type === 'text')
  const passwordInput = Array.from(allInputs).find((i) => i.type === 'password')
  return { usernameInput, passwordInput }
}

describe('LoginForm', () => {
  it('renders username and password fields', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    const { usernameInput, passwordInput } = getInputs()
    expect(usernameInput).toBeInTheDocument()
    expect(passwordInput).toBeInTheDocument()
  })

  it('pre-fills username with "admin"', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    const { usernameInput } = getInputs()
    expect(usernameInput).toHaveValue('admin')
  })

  it('password field starts empty', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    const { passwordInput } = getInputs()
    expect(passwordInput).toHaveValue('')
  })

  it('submit button is disabled when password is empty', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    expect(screen.getByRole('button', { name: /login/i })).toBeDisabled()
  })

  it('submit button is enabled when both fields are filled', async () => {
    const user = userEvent.setup()
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    const { passwordInput } = getInputs()
    await user.type(passwordInput, 'mypassword')
    expect(screen.getByRole('button', { name: /login/i })).toBeEnabled()
  })

  it('calls onLogin with username and password on submit', async () => {
    const onLogin = vi.fn().mockResolvedValue(undefined)
    const user = userEvent.setup()
    render(<LoginForm onLogin={onLogin} isLoading={false} />)
    const { passwordInput } = getInputs()
    await user.type(passwordInput, 'secret')
    await user.click(screen.getByRole('button', { name: /login/i }))
    expect(onLogin).toHaveBeenCalledWith('admin', 'secret')
  })

  it('shows "Accesso in corso..." when isLoading is true', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={true} />)
    expect(screen.getByRole('button', { name: /accesso in corso/i })).toBeInTheDocument()
  })

  it('disables inputs when isLoading is true', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={true} />)
    const { usernameInput, passwordInput } = getInputs()
    expect(usernameInput).toBeDisabled()
    expect(passwordInput).toBeDisabled()
  })

  it('disables submit button when isLoading is true', () => {
    render(<LoginForm onLogin={vi.fn()} isLoading={true} />)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('allows changing the username field', async () => {
    const user = userEvent.setup()
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    const { usernameInput } = getInputs()
    await user.clear(usernameInput)
    await user.type(usernameInput, 'newuser')
    expect(usernameInput).toHaveValue('newuser')
  })

  it('submit button is disabled when username is cleared', async () => {
    const user = userEvent.setup()
    render(<LoginForm onLogin={vi.fn()} isLoading={false} />)
    const { usernameInput, passwordInput } = getInputs()
    await user.type(passwordInput, 'pass')
    await user.clear(usernameInput)
    expect(screen.getByRole('button', { name: /login/i })).toBeDisabled()
  })
})
