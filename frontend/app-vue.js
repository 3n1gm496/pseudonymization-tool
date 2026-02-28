/**
 * Vue.js application for Local Pseudonymization Tool
 * Provides reactive state management and WebSocket real-time updates
 */

const { createApp } = Vue;

createApp({
    data() {
        return {
            // File selection
            selectedFiles: [],
            dragOver: false,
            
            // Configuration
            mode: 'light',
            passphrase: '',
            showPassphrase: false,
            dryRun: false,
            
            // Processing state
            processing: false,
            batchId: null,
            batchProcessing: false,
            
            // WebSocket progress
            currentProgress: 0,
            totalFiles: 0,
            progressMessage: 'Preparazione...',
            findingsCount: 0,
            
            // WebSocket connection
            ws: null,
        };
    },
    
    computed: {
        canStartBatch() {
            return this.selectedFiles.length > 0 && 
                   this.passphrase.length >= 8 && 
                   !this.processing;
        },
        
        progressPercentage() {
            if (this.totalFiles === 0) return 0;
            return Math.round((this.currentProgress / this.totalFiles) * 100);
        },
        
        passphraseStrength() {
            const len = this.passphrase.length;
            if (len === 0) return { text: '', class: '' };
            if (len < 8) return { text: '❌ Troppo corta (min 8 caratteri)', class: 'weak' };
            if (len < 12) return { text: '⚠️ Media', class: 'medium' };
            if (len < 16) return { text: '✅ Buona', class: 'strong' };
            return { text: '✅ Eccellente', class: 'excellent' };
        }
    },
    
    methods: {
        // File handling
        handleFileSelect(event) {
            const files = Array.from(event.target.files);
            this.addFiles(files);
        },
        
        handleDrop(event) {
            this.dragOver = false;
            const files = Array.from(event.dataTransfer.files);
            this.addFiles(files);
        },
        
        addFiles(newFiles) {
            const SUPPORTED_EXTS = ['txt', 'md', 'csv', 'docx', 'pdf', 'xlsx', 'jpg', 'jpeg', 'png'];
            const MAX_SIZE = 50 * 1024 * 1024; // 50 MB
            
            for (const file of newFiles) {
                const ext = file.name.split('.').pop().toLowerCase();
                
                if (!SUPPORTED_EXTS.includes(ext)) {
                    this.showToast(`Formato non supportato: ${file.name}`, 'warning');
                    continue;
                }
                
                if (file.size > MAX_SIZE) {
                    this.showToast(`File troppo grande (max 50 MB): ${file.name}`, 'warning');
                    continue;
                }
                
                // Check for duplicates
                const isDuplicate = this.selectedFiles.some(f => 
                    f.name === file.name && f.size === file.size
                );
                
                if (isDuplicate) {
                    this.showToast(`File già selezionato: ${file.name}`, 'info');
                    continue;
                }
                
                this.selectedFiles.push(file);
            }
            
            if (newFiles.length > 0) {
                this.showToast(`${newFiles.length} file aggiunti`, 'success');
            }
        },
        
        removeFile(index) {
            this.selectedFiles.splice(index, 1);
        },
        
        // Batch processing
        async startBatch() {
            if (!this.canStartBatch) return;
            
            this.processing = true;
            
            try {
                // Create FormData
                const formData = new FormData();
                
                for (const file of this.selectedFiles) {
                    formData.append('files', file);
                }
                
                formData.append('mode', this.mode);
                formData.append('passphrase', this.passphrase);
                formData.append('dry_run', this.dryRun);
                
                // Submit batch
                const response = await fetch('/api/batch', {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    throw new Error(error.detail || 'Errore durante la creazione del batch');
                }
                
                const result = await response.json();
                this.batchId = result.batch_id;
                
                // Initialize progress tracking
                this.batchProcessing = true;
                this.currentProgress = 0;
                this.totalFiles = this.selectedFiles.length;
                this.findingsCount = 0;
                this.progressMessage = 'Connessione al server...';
                
                // Connect WebSocket for real-time updates
                this.connectWebSocket(this.batchId);
                
                this.showToast('Batch avviato con successo!', 'success');
                
            } catch (error) {
                console.error('Errore:', error);
                this.showToast(error.message, 'error');
                this.processing = false;
            }
        },
        
        // WebSocket handling
        connectWebSocket(batchId) {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/api/ws/batch/${batchId}`;
            
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket connected');
                this.progressMessage = 'Connesso - In attesa di aggiornamenti...';
                
                // Send periodic ping to keep connection alive
                this.pingInterval = setInterval(() => {
                    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send('ping');
                    }
                }, 15000);
            };
            
            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.progressMessage = '⚠️ Errore di connessione';
            };
            
            this.ws.onclose = () => {
                console.log('WebSocket disconnected');
                if (this.pingInterval) {
                    clearInterval(this.pingInterval);
                }
            };
        },
        
        handleWebSocketMessage(data) {
            switch (data.type) {
                case 'progress':
                    this.currentProgress = data.progress;
                    this.totalFiles = data.total_files;
                    this.findingsCount = data.findings_count || 0;
                    this.progressMessage = `Elaborazione ${data.file_name}...`;
                    break;
                
                case 'complete':
                    this.progressMessage = '✅ Elaborazione completata!';
                    this.processing = false;
                    this.showToast('Batch completato con successo!', 'success');
                    
                    setTimeout(() => {
                        this.batchProcessing = false;
                        // Optionally redirect or show results
                    }, 3000);
                    break;
                
                case 'error':
                    this.progressMessage = `❌ Errore: ${data.error}`;
                    this.processing = false;
                    this.showToast(data.error, 'error');
                    break;
                
                case 'pong':
                case 'keepalive':
                    // Acknowledge keepalive
                    break;
                
                default:
                    console.log('Unknown message type:', data.type);
            }
        },
        
        closeProgressWidget() {
            this.batchProcessing = false;
            if (this.ws) {
                this.ws.close();
                this.ws = null;
            }
        },
        
        // Utility methods
        getFileIcon(name) {
            const ext = name.split('.').pop().toLowerCase();
            const icons = {
                txt: '📄', md: '📝', csv: '📊', docx: '📘', pdf: '📕',
                xlsx: '📗', jpg: '🖼️', jpeg: '🖼️', png: '🖼️',
            };
            return icons[ext] || '📄';
        },
        
        formatBytes(bytes) {
            if (bytes < 1024) return bytes + ' B';
            if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
            return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
        },
        
        showToast(msg, type = 'info', duration = 4000) {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            toast.className = `toast ${type}`;
            toast.textContent = msg;
            container.appendChild(toast);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transition = 'opacity 0.3s';
                setTimeout(() => toast.remove(), 300);
            }, duration);
        }
    },
    
    beforeUnmount() {
        // Clean up WebSocket connection
        if (this.ws) {
            this.ws.close();
        }
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
        }
    }
}).mount('#app');
