/**
 * Domain types for the Pseudonymization Tool frontend.
 *
 * These types mirror the backend Pydantic schemas and are used throughout
 * the React application for type-safe data handling.
 */

/** A single entity detected in text or files that may need pseudonymisation. */
export interface Finding {
  /** Unique finding identifier */
  finding_id: string
  /** Entity category (e.g. "EMAIL", "IP_ADDRESS") */
  entity_type: string
  /** Original value found in text/file */
  original_value: string
  /** Suggested pseudonym replacement */
  proposed_pseudonym: string
  /** Detection confidence (0.0–1.0) */
  confidence_score: number
  /** Name of detector that found this entity */
  detector_name: string
  /** File ID if from file scan */
  file_id?: string
  /** User-modified pseudonym */
  modified_pseudonym?: string
  /** Review action: "accept", "reject", or "modify" */
  review_action: 'accept' | 'reject' | 'modify'
  /** Whether finding is from text input vs file */
  is_text_input?: boolean
}

/** A file uploaded to a batch for scanning. */
export interface FileRecord {
  /** Unique file identifier */
  file_id: string
  /** Original filename */
  original_name: string
  /** File extension */
  extension: string
  /** File size in bytes */
  size_bytes: number
  /** File processing status */
  status: string
  /** Number of findings in this file */
  findings_count: number
  /** Error message if processing failed */
  error_message?: string
}

/** Processing mode for pseudonymisation. */
export type BatchMode = 'light' | 'strict'

/** Detection preset name. */
export type PresetName = 'SOC Logs' | 'Policy Docs' | 'Email Headers'

/** Current status of batch processing. */
export type BatchStatus = 'PENDING' | 'SCANNING' | 'REVIEW' | 'APPLYING' | 'DONE' | 'FAILED'

/** Safety classification for batch content. */
export type SafetyLabel = 'SAFE_TO_UPLOAD' | 'SAFE_WITH_WARNINGS' | 'NOT_SAFE'

/** Batch configuration options. */
export interface BatchConfig {
  /** Processing mode */
  mode: BatchMode
  /** Detection preset (server-side default: 'SOC Logs') */
  preset: PresetName
}

/** A pseudonymisation batch. */
export interface Batch {
  /** Unique batch identifier (UUID) */
  batch_id: string
  /** Current processing status */
  status: BatchStatus
  /** All findings detected in batch */
  findings: Finding[]
  /** Files in batch */
  files: FileRecord[]
  /** Batch configuration */
  config: BatchConfig
  /** Safety classification */
  safety_label: SafetyLabel
  /** True if batch from text scan */
  is_text_input?: boolean
  /** Original text if text scan */
  source_text?: string
  /** ISO timestamp of creation */
  created_at?: string
}

/** A review decision for a single finding. */
export interface ReviewDecision {
  /** Finding being reviewed */
  finding_id: string
  /** Review action */
  action: 'accept' | 'reject' | 'modify'
  /** Custom pseudonym if action is modify */
  custom_pseudonym?: string
}

/** Parameters for applying pseudonymisation to a batch. */
export interface ApplyRequest {
  /** Batch ID to apply */
  batchId: string
  /** File ID (for file batches) */
  fileId: string
  /** Whether batch is text input */
  isTextInput: boolean
  /** Source text if text input */
  sourceText: string
}

/** Toast notification options. */
export interface ToastOptions {
  /** Toast notification type */
  type: 'success' | 'error' | 'warning' | 'info'
}

/** Toast notification type alias. */
export type ToastType = ToastOptions['type']

/** A single toast notification. */
export interface Toast {
  id: number
  message: string
  type: ToastType
}

/** Audit log event from the backend. */
export interface AuditEvent {
  id: number
  timestamp: string
  action: string
  user: string | null
  ip: string | null
  details: Record<string, unknown>
}

/** Paginated audit events response. */
export interface AuditEventsResponse {
  events: AuditEvent[]
  total: number
  offset: number
  limit: number
}

/** LDAP configuration. */
export interface LDAPConfig {
  configured: boolean
  host?: string
  port?: number
  base_dn?: string
  bind_dn?: string
  search_filter?: string
  use_ssl?: boolean
  starttls?: boolean
  tls_validate_cert?: boolean
  diagnostics?: Record<string, unknown> | null
  /** Authentication via LDAP (eDirectory) */
  auth_enabled?: boolean
  auth_user_base_dn?: string
  auth_admin_group_dn?: string
  auth_operator_group_dn?: string
  auth_default_role?: 'admin' | 'operator'
}

/** LDAP test result. */
export interface LDAPTestResult {
  ok: boolean
  error?: string
  user_count?: number
}

/** User role in the system. */
export type UserRole = 'admin' | 'operator'

/** A local user account. */
export interface User {
  username: string
  role: UserRole
  created_at: string
  updated_at: string
  is_active: number
}

/** Response from GET /api/users */
export interface UsersListResponse {
  users: User[]
  total: number
}

/** Currently authenticated user info from GET /api/users/me */
export interface CurrentUser {
  username: string
  role: UserRole
}

/** Revert preview result. */
export interface RevertPreview {
  files: Array<{
    original_name: string
    status: string
    replacements_count?: number
  }>
}
