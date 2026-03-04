/**
 * Configured axios instance with CSRF protection.
 *
 * Features:
 * - withCredentials enabled for session cookies
 * - CSRF token interceptor for POST/DELETE/PATCH/PUT requests
 * - Automatic token refresh from response headers
 */
import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'

// Store CSRF token in memory (cleared on refresh)
let csrfToken: string | null = null

/**
 * Set the CSRF token in memory.
 */
export function setCsrfToken(token: string | null): void {
  if (token) {
    csrfToken = token
  }
}

/**
 * Get the current CSRF token.
 */
export function getCsrfToken(): string | null {
  return csrfToken
}

/**
 * Create configured axios instance.
 */
const axiosInstance = axios.create({
  withCredentials: true,
})

/**
 * Response interceptor to capture CSRF token from headers.
 * Backend sets X-CSRF-Token in response after successful login.
 */
axiosInstance.interceptors.response.use(
  (response: AxiosResponse) => {
    // Extract CSRF token from response header if present
    const tokenFromResponse = response.headers['x-csrf-token'] as string | undefined
    if (tokenFromResponse) {
      setCsrfToken(tokenFromResponse)
    }
    return response
  },
  (error: unknown) => {
    // Re-throw error for caller to handle
    return Promise.reject(error)
  },
)

/**
 * Request interceptor to add CSRF token to POST/DELETE/PATCH/PUT requests.
 * CSRF Protection — Frontend implementation.
 */
axiosInstance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // Only add CSRF token for state-changing methods
    const statefulMethods = ['POST', 'DELETE', 'PATCH', 'PUT']
    if (config.method && statefulMethods.includes(config.method.toUpperCase())) {
      if (csrfToken) {
        // Add token to X-CSRF-Token header (standard location)
        config.headers['X-CSRF-Token'] = csrfToken
      }
    }
    return config
  },
  (error: unknown) => {
    return Promise.reject(error)
  },
)

export default axiosInstance
