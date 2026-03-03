/**
 * Configured axios instance with CSRF protection
 * 
 * Features:
 * - withCredentials enabled for session cookies
 * - CSRF token interceptor for POST/DELETE/PATCH/PUT requests
 * - Automatic token refresh from response headers
 */

import axios from 'axios'

// Store CSRF token in memory (cleared on refresh)
let csrfToken = null

/**
 * Extract CSRF token from response headers or set from parameter
 */
export function setCsrfToken(token) {
  if (token) {
    csrfToken = token
  }
}

/**
 * Get current CSRF token
 */
export function getCsrfToken() {
  return csrfToken
}

/**
 * Create configured axios instance
 */
const axiosInstance = axios.create({
  withCredentials: true,
})

/**
 * Response interceptor to capture CSRF token from headers
 * Backend sets X-CSRF-Token in response after successful login
 */
axiosInstance.interceptors.response.use(
  (response) => {
    // Extract CSRF token from response header if present
    const tokenFromResponse = response.headers['x-csrf-token']
    if (tokenFromResponse) {
      setCsrfToken(tokenFromResponse)
    }
    return response
  },
  (error) => {
    // Re-throw error for caller to handle
    return Promise.reject(error)
  }
)

/**
 * Request interceptor to add CSRF token to POST/DELETE/PATCH/PUT requests
 * CSRF Protection - Frontend implementation
 */
axiosInstance.interceptors.request.use(
  (config) => {
    // Only add CSRF token for state-changing methods
    const statefulMethods = ['POST', 'DELETE', 'PATCH', 'PUT']
    if (statefulMethods.includes(config.method.toUpperCase())) {
      if (csrfToken) {
        // Add token to X-CSRF-Token header (standard location)
        config.headers['X-CSRF-Token'] = csrfToken
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

export default axiosInstance
