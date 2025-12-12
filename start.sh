#!/bin/bash
# start.sh - Exécution simplifiée

echo "📧 LANCEMENT DU SCRIPT D'ENVOI D'EMAILS"
echo "======================================"

# Vérifier si on est root
if [ "$EUID" -ne 0 ]; then 
    echo "⚠️  Ce script nécessite des privilèges sudo."
    echo "🔧 Exécution avec sudo..."
    sudo python3 send.py "$@"
else
    python3 send.py "$@"
fi
