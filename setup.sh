#!/bin/bash
# setup.sh - Installation rapide pour Google Cloud Shell

echo "🔧 Installation du script d'envoi d'emails..."
echo "============================================"

# Mettre à jour et installer les dépendances
echo "📦 Mise à jour des paquets..."
sudo apt-get update -y

echo "📦 Installation des dépendances..."
sudo apt-get install -y postfix mailutils

# Créer les fichiers de configuration
echo "📄 Création des fichiers de configuration..."
cat > 0-header.txt << 'EOF'
From: Votre Nom <votre@email.com>
Subject: Votre sujet d'email
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8
EOF

cat > 1-data.txt << 'EOF'
test1@example.com
test2@example.com
test3@example.com
EOF

cat > 2-body.html << 'EOF'
<!DOCTYPE html>
<html>
<body>
<h1>Bonjour !</h1>
<p>Ceci est un email de test depuis Google Cloud Shell.</p>
<p>Email: {{email}}</p>
<p>Date: {{timestamp}}</p>
</body>
</html>
EOF

cat > 3-testafter.txt << 'EOF'
test_interval:100

Adresses de test:
votre.email@gmail.com

Message après envoi:
✅ Envoi terminé avec succès !
EOF

# Télécharger le script principal
echo "📥 Téléchargement du script principal..."
curl -o send.py https://raw.githubusercontent.com/votre-repo/send.py/main/send.py

# Rendre le script exécutable
chmod +x send.py

echo ""
echo "✅ Installation terminée !"
echo ""
echo "📝 FICHIERS CRÉÉS:"
echo "   0-header.txt    - Configuration de l'expéditeur"
echo "   1-data.txt      - Liste d'emails"
echo "   2-body.html     - Template HTML"
echo "   3-testafter.txt - Configuration des tests"
echo "   send.py         - Script principal"
echo ""
echo "🎯 POUR COMMENCER:"
echo "   1. Éditez les fichiers de configuration"
echo "   2. Testez: sudo python3 send.py --test"
echo "   3. Lancez: sudo python3 send.py"
