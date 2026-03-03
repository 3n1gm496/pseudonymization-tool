/**
 * @fileoverview Type definitions for Pseudonymization Tool frontend
 * Provides JSDoc type safety for components without migrating to TypeScript
 */

/**
 * @typedef {Object} Finding
 * @property {string} finding_id - Unique identifier for the finding
 * @property {string} entity_type - Type of entity (e.g., "PERSON", "EMAIL", "HOSTNAME")
 * @property {string} original_value - Original value found in text/file
 * @property {string} proposed_pseudonym - Suggested pseudonym replacement
 * @property {number} confidence_score - Detection confidence (0.0-1.0)
 * @property {string} detector_name - Name of detector that found this entity
 * @property {string} [file_id] - File ID if from file scan
 * @property {string} [modified_pseudonym] - User-modified pseudonym
 * @property {string} review_action - Review action: "accept", "reject", "modify"
 * @property {boolean} [is_text_input] - Whether finding is from text input vs file
 */

/**
 * @typedef {Object} FileRecord
 * @property {string} file_id - Unique file identifier
 * @property {string} original_name - Original filename
 * @property {string} extension - File extension
 * @property {number} size_bytes - File size in bytes
 * @property {string} status - File processing status
 * @property {number} findings_count - Number of findings in this file
 * @property {string} [error_message] - Error message if processing failed
 */

/**
 * @typedef {'light'|'strict'} BatchMode
 * Mode for pseudonymization processing
 */

/**
 * @typedef {'SOC Logs'|'Policy Docs'|'Email Headers'} PresetName
 * Detection preset — applied automatically by the backend (default: 'SOC Logs').
 * The frontend does not expose a preset selector; the value is fixed server-side.
 * Available presets are listed by GET /api/settings/policies.
 */

/**
 * @typedef {'PENDING'|'SCANNING'|'REVIEW'|'APPLYING'|'DONE'|'FAILED'} BatchStatus
 * Current status of batch processing
 */

/**
 * @typedef {'SAFE_TO_UPLOAD'|'SAFE_WITH_WARNINGS'|'NOT_SAFE'} SafetyLabel
 * Safety classification for batch content
 */

/**
 * @typedef {Object} BatchConfig
 * @property {BatchMode} mode - Processing mode
 * @property {PresetName} preset - Detection preset (server-side default: 'SOC Logs')
 */

/**
 * @typedef {Object} Batch
 * @property {string} batch_id - Unique batch identifier (UUID)
 * @property {BatchStatus} status - Current processing status
 * @property {Finding[]} findings - All findings detected in batch
 * @property {FileRecord[]} files - Files in batch
 * @property {BatchConfig} config - Batch configuration
 * @property {SafetyLabel} safety_label - Safety classification
 * @property {boolean} [is_text_input] - True if batch from text scan
 * @property {string} [source_text] - Original text if text scan
 * @property {string} [created_at] - ISO timestamp of creation
 */

/**
 * @typedef {Object} ReviewDecision
 * @property {string} finding_id - Finding being reviewed
 * @property {'accept'|'reject'|'modify'} action - Review action
 * @property {string} [custom_pseudonym] - Custom pseudonym if action is modify
 */

/**
 * @typedef {Object} ApplyRequest
 * @property {string} batchId - Batch ID to apply
 * @property {string} fileId - File ID (for file batches)
 * @property {boolean} isTextInput - Whether batch is text input
 * @property {string} sourceText - Source text if text input
 */

/**
 * @typedef {Object} ToastOptions
 * @property {'success'|'error'|'warning'|'info'} type - Toast notification type
 */

export {}
