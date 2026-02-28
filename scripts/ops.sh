#!/bin/bash
# Operazioni Pseudonymization Tool su Docker Compose
# Provvede comandi standard: up, down, logs, health, status

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROFILE="${PROFILE:---profile dev}"

# Colori ANSI
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
info() {
    echo -e "${BLUE}ℹ ${1}${NC}"
}

success() {
    echo -e "${GREEN}✓ ${1}${NC}"
}

warning() {
    echo -e "${YELLOW}⚠ ${1}${NC}"
}

error() {
    echo -e "${RED}✗ ${1}${NC}" >&2
}

# Verifica Docker e Docker Compose
check_prerequisites() {
    if ! command -v docker &> /dev/null; then
        error "Docker non installato. Installa Docker e riprova."
        exit 1
    fi
    if ! command -v docker compose &> /dev/null; then
        error "Docker Compose non installato. Installa Docker Compose e riprova."
        exit 1
    fi
    info "Docker e Docker Compose disponibili."
}

# Avvio container
cmd_up() {
    local profile="${1:---profile dev}"
    info "Avvio container (profilo: ${profile})..."
    cd "$PROJECT_DIR"
    docker compose $profile up -d --build
    success "Container avviato."
    info "Accedi via http://127.0.0.1:8000"
}

# Stop container
cmd_down() {
    info "Arresto container..."
    cd "$PROJECT_DIR"
    docker compose down
    success "Container fermato."
}

# Log in tempo reale
cmd_logs() {
    info "Log in tempo reale (Ctrl+C per uscire)..."
    cd "$PROJECT_DIR"
    docker compose logs -f pseudonymization-tool
}

# Status
cmd_status() {
    info "Stato container:"
    cd "$PROJECT_DIR"
    docker compose ps
}

# Health check
cmd_health() {
    info "Esecuzione health check..."
    if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        success "Health check: OK"
        curl -sS http://127.0.0.1:8000/api/health | jq . || echo "Error parsing response"
    else
        error "Health check: FAILED"
        return 1
    fi
}

# Readiness check
cmd_readiness() {
    info "Esecuzione readiness check..."
    if curl -fsS http://127.0.0.1:8000/api/ready >/dev/null 2>&1; then
        success "Readiness check: OK"
        curl -sS http://127.0.0.1:8000/api/ready | jq . || echo "Error parsing response"
    else
        error "Readiness check: FAILED"
        return 1
    fi
}

# Test e-2-e veloce
cmd_test() {
    info "Esecuzione test e2e (scanione testo di prova)..."
    local test_text="Email: test@example.com, IP: 192.168.1.1"
    response=$(curl -s -X POST http://127.0.0.1:8000/api/console/scan \
        -H "Content-Type: application/json" \
        -d "{\"text\": \"$test_text\", \"mode\": \"light\", \"preset\": \"SOC Logs\"}")
    
    if echo "$response" | jq . >/dev/null 2>&1; then
        success "Test e2e: PASSED"
        echo "$response" | jq .
    else
        error "Test e2e: FAILED"
        echo "$response"
        return 1
    fi
}

# Reset (cancella dati temporanei)
cmd_reset() {
    warning "Reset: cancellera' tutti i dati temporanei (Ctrl+C per annullare)..."
    sleep 2
    info "Arresto container..."
    cd "$PROJECT_DIR"
    docker compose down -v
    success "Reset completato."
}

# Help
cmd_help() {
    cat <<EOF
Pseudonymization Tool — Docker Compose Operations

Uso: ./scripts/ops.sh <comando> [opzioni]

Comandi:
  up [profilo]     Avvia container (predefinito: --profile dev)
                   Opzioni profilo: '--profile dev' o '--profile prod'
  down             Arresta container
  logs             Visualizza log in tempo reale
  status           Mostra stato container
  health           Esegui health check API
  ready            Esegui readiness check API
  test             Esegui test e2e scanione
  reset            Arresta e cancella dati temporanei (DESTRUCTIVE)
  help             Mostra questo messaggio

Variabili ambiente:
  PROFILE          Profilo compose (default: '--profile dev')

Esempi:
  ./scripts/ops.sh up
  ./scripts/ops.sh up --profile prod
  ./scripts/ops.sh logs
  ./scripts/ops.sh health
  PROFILE='--profile prod' ./scripts/ops.sh up

EOF
}

# Main
main() {
    check_prerequisites
    
    local cmd="${1:-help}"
    shift || true
    
    case "$cmd" in
        up)
            cmd_up "$@"
            ;;
        down)
            cmd_down
            ;;
        logs)
            cmd_logs
            ;;
        status|ps)
            cmd_status
            ;;
        health)
            cmd_health
            ;;
        ready|readiness)
            cmd_readiness
            ;;
        test|e2e)
            cmd_test
            ;;
        reset)
            cmd_reset
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            error "Comando sconosciuto: $cmd"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
