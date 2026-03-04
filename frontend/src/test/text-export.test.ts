/**
 * Tests for utils/text-export.ts
 * Covers: copyToClipboard, downloadTextFile, downloadBinaryFile
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { copyToClipboard, downloadTextFile, downloadBinaryFile } from '../utils/text-export'

describe('copyToClipboard', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn() },
      writable: true,
      configurable: true,
    })
  })

  it('returns true when clipboard write succeeds', async () => {
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined)
    const result = await copyToClipboard('hello world')
    expect(result).toBe(true)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('hello world')
  })

  it('returns false when clipboard write fails', async () => {
    vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('Permission denied'))
    const result = await copyToClipboard('hello world')
    expect(result).toBe(false)
  })

  it('copies empty string', async () => {
    vi.mocked(navigator.clipboard.writeText).mockResolvedValue(undefined)
    const result = await copyToClipboard('')
    expect(result).toBe(true)
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('')
  })
})

describe('downloadTextFile', () => {
  let mockAnchor: { href: string; download: string; click: ReturnType<typeof vi.fn> }
  let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    mockAnchor = { href: '', download: '', click: vi.fn() }
    vi.spyOn(window.URL, 'createObjectURL').mockReturnValue('blob:mock-url')
    revokeObjectURLSpy = vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(document, 'createElement').mockReturnValue(mockAnchor as unknown as HTMLElement)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a download link and clicks it', () => {
    downloadTextFile('test content', 'output.txt')
    expect(mockAnchor.download).toBe('output.txt')
    expect(mockAnchor.href).toBe('blob:mock-url')
    expect(mockAnchor.click).toHaveBeenCalledOnce()
  })

  it('uses default filename when not provided', () => {
    downloadTextFile('test content')
    expect(mockAnchor.download).toBe('export.txt')
  })

  it('revokes the object URL after download', () => {
    downloadTextFile('test content', 'file.txt')
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:mock-url')
  })

  it('creates a download link with the correct filename', () => {
    downloadTextFile('my text', 'custom-name.txt')
    expect(mockAnchor.download).toBe('custom-name.txt')
    expect(mockAnchor.click).toHaveBeenCalledOnce()
  })
})

describe('downloadBinaryFile', () => {
  let mockAnchor: { href: string; download: string; click: ReturnType<typeof vi.fn> }
  let createObjectURLSpy: ReturnType<typeof vi.spyOn>
  let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    mockAnchor = { href: '', download: '', click: vi.fn() }
    createObjectURLSpy = vi
      .spyOn(window.URL, 'createObjectURL')
      .mockReturnValue('blob:binary-url')
    revokeObjectURLSpy = vi.spyOn(window.URL, 'revokeObjectURL').mockImplementation(() => {})
    vi.spyOn(document, 'createElement').mockReturnValue(mockAnchor as unknown as HTMLElement)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('creates a download link for a binary blob', () => {
    const blob = new Blob(['binary data'])
    downloadBinaryFile(blob, 'archive.zip')
    expect(createObjectURLSpy).toHaveBeenCalledWith(blob)
    expect(mockAnchor.download).toBe('archive.zip')
    expect(mockAnchor.click).toHaveBeenCalledOnce()
  })

  it('uses default filename when not provided', () => {
    downloadBinaryFile(new Blob(['data']))
    expect(mockAnchor.download).toBe('download.bin')
  })

  it('revokes the object URL after download', () => {
    downloadBinaryFile(new Blob(['data']), 'file.bin')
    expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:binary-url')
  })
})
