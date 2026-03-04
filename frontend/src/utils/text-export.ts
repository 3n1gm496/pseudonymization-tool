/**
 * Utility functions for copying text and downloading files.
 */

/**
 * Copy text to the system clipboard.
 *
 * @returns `true` on success, `false` if the Clipboard API is unavailable or
 *          the user denied permission.
 */
export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (err) {
    console.error('Failed to copy to clipboard:', err)
    return false
  }
}

/**
 * Trigger a browser download of a plain-text string.
 *
 * @param text     Content to download.
 * @param filename Suggested filename (default: `'export.txt'`).
 */
export const downloadTextFile = (text: string, filename = 'export.txt'): void => {
  const blob = new Blob([text], { type: 'text/plain; charset=utf-8' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}

/**
 * Trigger a browser download of a binary `Blob`.
 *
 * @param blob     Binary content to download.
 * @param filename Suggested filename (default: `'download.bin'`).
 */
export const downloadBinaryFile = (blob: Blob, filename = 'download.bin'): void => {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}
