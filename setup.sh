# Installation initiale
sudo apt-get update
sudo apt-get install -y python3 python3-pip postfix mailutils
pip3 install sqlite3

# Configuration
mkdir -p config/email_lists
mkdir -p config/templates

# Copier vos fichiers
cp vos_emails.txt config/email_lists/
cp vos_templates/*.html config/templates/

# Lancer avec sudo
sudo python3 send.py config --create-default
sudo python3 send.py add --email-list "Ma liste" config/email_lists/vos_emails.txt

# Lancer l'envoi (reprise automatique si interruption)
sudo python3 send.py send --list-name "Ma liste" --pause-after 100
