#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# generate-dev-certs.sh — Genera certificati TLS self-signed per sviluppo/staging
# ═══════════════════════════════════════════════════════════════════════════════
#
# Genera un certificato self-signed valido per localhost e 127.0.0.1.
# NON usare in produzione: usare Let's Encrypt o certificati aziendali.
#
# Output:
#   nginx/certs/fullchain.pem  — certificato (chain)
#   nginx/certs/privkey.pem    — chiave privata
#
# Uso:
#   bash scripts/generate-dev-certs.sh
#
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CERTS_DIR="$PROJECT_ROOT/nginx/certs"

echo "🔐 Generazione certificati TLS self-signed per sviluppo..."
echo "   Output: $CERTS_DIR"

mkdir -p "$CERTS_DIR"

# Genera chiave privata RSA 4096-bit e certificato self-signed
openssl req \
    -x509 \
    -nodes \
    -days 365 \
    -newkey rsa:4096 \
    -keyout "$CERTS_DIR/privkey.pem" \
    -out "$CERTS_DIR/fullchain.pem" \
    -subj "/C=IT/ST=Local/L=Local/O=Pseudonymization Tool Dev/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,DNS:pseudonymization-tool,IP:127.0.0.1"

chmod 600 "$CERTS_DIR/privkey.pem"
chmod 644 "$CERTS_DIR/fullchain.pem"

echo ""
echo "✓ Certificati generati:"
echo "   $CERTS_DIR/fullchain.pem"
echo "   $CERTS_DIR/privkey.pem"
echo ""
echo "⚠️  ATTENZIONE: Questi certificati sono self-signed e validi solo per sviluppo."
echo "   Per produzione, usare Let's Encrypt:"
echo "   sudo certbot certonly --standalone -d your-domain.com"
echo "   Poi copiare fullchain.pem e privkey.pem in nginx/certs/"
echo ""
echo "   Per avviare con nginx:"
echo "   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
