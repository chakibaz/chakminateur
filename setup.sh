#!/bin/bash
# setup.sh - Installation complète en un clic

echo "🚀 INSTALLATION DU SCRIPT D'ENVOI D'EMAILS INTELLIGENT"
echo "======================================================"

# 1. Mettre à jour le système
echo "📦 Mise à jour du système..."
sudo apt-get update -y

# 2. Installer les dépendances
echo "📦 Installation des dépendances..."
sudo apt-get install -y postfix mailutils sqlite3 python3 python3-pip

# 3. Télécharger le script principal
echo "📥 Téléchargement du script..."
curl -o send.py https://raw.githubusercontent.com/votre-repo/email-sender/main/send.py
chmod +x send.py

# 4. Créer la structure de dossiers
echo "📁 Création de la structure..."
mkdir -p config/email_lists
mkdir -p config/templates

# 5. Créer les fichiers de configuration par défaut
echo "⚙️  Configuration par défaut..."
sudo python3 send.py config --create-default

# 6. Créer des exemples
echo "📝 Création d'exemples..."

# Liste d'emails exemple
cat > config/email_lists/exemple.txt << 'EOF'
email1@example.com
email2@example.com
email3@example.com
email4@example.com
email5@example.com
EOF

# Template HTML exemple
cat > config/templates/promo1.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Promotion Spéciale</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #e74c3c;">🎉 PROMOTION EXCEPTIONNELLE !</h1>
        <p>Cher client,</p>
        <p>Nous avons une offre spéciale pour vous :</p>
        <div style="background-color: #f8f9fa; padding: 15px; margin: 15px 0; border-left: 4px solid #3498db;">
            <p><strong>Email:</strong> {{email}}</p>
            <p><strong>Date:</strong> {{timestamp}}</p>
            <p><strong>Référence:</strong> {{template_name}}</p>
        </div>
        <p>Ne manquez pas cette opportunité unique !</p>
        <p>Cordialement,<br>L'équipe commerciale</p>
    </div>
</body>
</html>
EOF

# Template HTML exemple 2
cat > config/templates/newsletter.html << 'EOF'
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Newsletter</title>
</head>
<body style="font-family: Georgia, serif;">
    <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd;">
        <div style="background-color: #2c3e50; color: white; padding: 20px; text-align: center;">
            <h1>📰 NEWSLETTER</h1>
        </div>
        <div style="padding: 30px;">
            <p>Bonjour,</p>
            <p>Voici les dernières nouvelles de notre newsletter :</p>
            <ul style="padding-left: 20px;">
                <li>Nouveaux produits disponibles</li>
                <li>Offres spéciales du mois</li>
                <li>Événements à venir</li>
            </ul>
            <p><strong>Destinataire:</strong> {{email}}</p>
            <p><strong>Envoyé le:</strong> {{timestamp}}</p>
            <p>Restez connecté pour plus d'actualités !</p>
            <p>À bientôt,<br>L'équipe communication</p>
        </div>
    </div>
</body>
</html>
EOF

# 7. Configurer Postfix pour Google Cloud Shell
echo "🔧 Configuration de Postfix..."
sudo tee /etc/postfix/main.cf > /dev/null << 'EOF'
# Postfix configuration for Google Cloud Shell
myhostname = localhost
inet_interfaces = loopback-only
inet_protocols = all
relayhost = 
mydestination = localhost
smtp_sasl_auth_enable = no
smtpd_sasl_auth_enable = no
smtp_tls_security_level = none
mailbox_size_limit = 0
recipient_delimiter = +
disable_vrfy_command = yes
EOF

# 8. Redémarrer Postfix
echo "🔄 Redémarrage de Postfix..."
sudo service postfix restart 2>/dev/null || sudo postfix restart 2>/dev/null || true

# 9. Tester l'installation
echo "🧪 Test de l'installation..."
python3 send.py test --email test@localhost

echo ""
echo "✅ INSTALLATION TERMINÉE !"
echo ""
echo "📁 STRUCTURE CRÉÉE :"
echo "   send.py                    - Script principal"
echo "   config/                    - Dossier de configuration"
echo "   ├── config.json           - Configuration générale"
echo "   ├── email_manager.db      - Base de données"
echo "   ├── email_lists/          - Listes d'emails"
echo "   │   └── exemple.txt       - Liste d'exemple"
echo "   └── templates/            - Templates HTML"
echo "       ├── promo1.html       - Template promotion"
echo "       └── newsletter.html   - Template newsletter"
echo ""
echo "🎯 POUR COMMENCER :"
echo "   1. Éditez config/config.json"
echo "   2. Ajoutez vos emails dans config/email_lists/"
echo "   3. Testez : sudo python3 send.py test --email votre@email.com"
echo "   4. Lancez : sudo python3 send.py send"
