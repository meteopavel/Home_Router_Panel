#!/usr/bin/env bash
# gen-claude-ca.sh — корневой CA (nameConstraints → api.anthropic.com) + leaf.
#
# CA математически ограничен RFC 5280 Name Constraints: permitted;DNS:api.anthropic.com
# — физически не способен подписать сертификат для другого домена.
#
#   claude-api-ca.crt   → на клиентские машины (импорт в keychain с -p ssl)
#   claude-api.crt/.key → в nginx (TLS-терминация api.anthropic.com)
#
# Запуск на роутере (нужен openssl):
#   sudo bash scripts/gen-claude-ca.sh [/path/to/outdir]   # по умолчанию /etc/nginx/ssl

set -euo pipefail
OPENSSL="${OPENSSL:-openssl}"
OUTDIR="${1:-/etc/nginx/ssl}"
DOMAIN="api.anthropic.com"
mkdir -p "$OUTDIR"
cd "$OUTDIR"

echo "[*] openssl: $($OPENSSL version) | OUTDIR=$OUTDIR"

cat > _ca.cnf <<EOF
[req]
distinguished_name = dn
prompt = no
x509_extensions = v3_ca
[dn]
CN = Home Router Claude Redirect CA
[v3_ca]
basicConstraints = critical, CA:true
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
nameConstraints = critical, permitted;DNS:$DOMAIN
EOF

cat > _leaf.cnf <<EOF
[req]
distinguished_name = dn
prompt = no
req_extensions = v3_leaf
[dn]
CN = $DOMAIN
[v3_leaf]
basicConstraints = CA:false
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = DNS:$DOMAIN
EOF

echo "[*] root CA (nameConstraints → $DOMAIN)..."
$OPENSSL req -x509 -newkey rsa:4096 -nodes \
    -keyout claude-api-ca.key -out claude-api-ca.crt -days 3650 \
    -config _ca.cnf -extensions v3_ca 2>/dev/null
chmod 600 claude-api-ca.key

echo "[*] leaf (CN/SAN=$DOMAIN)..."
$OPENSSL req -newkey rsa:2048 -nodes \
    -keyout claude-api.key -out _leaf.csr -config _leaf.cnf 2>/dev/null
$OPENSSL x509 -req -in _leaf.csr \
    -CA claude-api-ca.crt -CAkey claude-api-ca.key -CAcreateserial \
    -days 825 -out claude-api.crt -extfile _leaf.cnf -extensions v3_leaf 2>/dev/null
chmod 600 claude-api.key
rm -f _leaf.csr _ca.cnf _leaf.cnf

echo "[*] chain verify:"; $OPENSSL verify -CAfile claude-api-ca.crt claude-api.crt
echo "[*] CA nameConstraints:"; $OPENSSL x509 -in claude-api-ca.crt -noout -text | grep -A3 -i "Name Constraints"
echo "[*] leaf SAN:"; $OPENSSL x509 -in claude-api.crt -noout -text | grep -A1 -i "Subject Alternative Name"
echo
echo "[✓] root:  $OUTDIR/claude-api-ca.crt  → копировать на клиенты (security add-trusted-cert -p ssl)"
echo "[✓] leaf:  $OUTDIR/claude-api.crt + claude-api.key  → nginx (ssl_certificate/_key)"
