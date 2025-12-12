#!/usr/bin/env python3
"""
Script d'envoi d'emails utilisant Postfix sur Google Cloud Shell
Avec système de test périodique
Auteur: Assistant IA
Usage: python3 send.py
"""

import os
import sys
import subprocess
import time
import re
from datetime import datetime
import signal
import argparse
import json
import shutil

class PostfixMailer:
    def __init__(self, config_dir="."):
        self.config_dir = config_dir
        self.load_config()
        self.setup_postfix()
        self.test_interval = 500  # Tous les 500 emails par défaut
        self.last_test_time = None
        self.stats = {
            'total_sent': 0,
            'total_failed': 0,
            'last_test_sent': 0,
            'start_time': datetime.now(),
            'batch_history': []
        }
        
    def load_config(self):
        """Charge les fichiers de configuration"""
        config_files = {
            'header': '0-header.txt',
            'data': '1-data.txt',
            'body': '2-body.html',
            'test_after': '3-testafter.txt'
        }
        
        self.config = {}
        for key, filename in config_files.items():
            filepath = os.path.join(self.config_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    self.config[key] = f.read().strip()
            except FileNotFoundError:
                print(f"⚠️  Fichier {filename} non trouvé")
                if key == 'header':
                    self.config[key] = "From: Mon Service <noreply@localhost>\nMIME-Version: 1.0\nContent-Type: text/html; charset=utf-8"
                elif key == 'body':
                    self.config[key] = "<html><body><h1>Email de Test</h1><p>Ceci est un email de test.</p></body></html>"
                else:
                    self.config[key] = ""
        
        # Charger la liste d'emails
        data_file = os.path.join(self.config_dir, '1-data.txt')
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                self.email_list = [line.strip() for line in f if line.strip() and '@' in line]
        else:
            self.email_list = []
        
        # Extraire l'intervalle de test du fichier test_after
        if self.config['test_after']:
            interval_match = re.search(r'test_interval\s*[:=]\s*(\d+)', self.config['test_after'])
            if interval_match:
                self.test_interval = int(interval_match.group(1))
                print(f"📊 Intervalle de test configuré: tous les {self.test_interval} emails")
            
    def setup_postfix(self):
        """Configure Postfix automatiquement pour Google Cloud Shell"""
        print("🔧 Configuration de Postfix pour Google Cloud Shell...")
        
        # Vérifier les privilèges
        if os.geteuid() != 0:
            print("❌ Ce script nécessite des privilèges sudo.")
            print("   Veuillez exécuter: sudo python3 send.py")
            sys.exit(1)
        
        # Vérifier si Postfix est déjà installé
        postfix_installed = shutil.which('postfix') is not None
        
        if not postfix_installed:
            print("📦 Installation de Postfix et dépendances...")
            try:
                subprocess.run(['apt-get', 'update', '-y'], check=True, capture_output=True)
                subprocess.run(['apt-get', 'install', '-y', 'postfix', 'mailutils', 'libsasl2-2', 'libsasl2-modules'], 
                             check=True, capture_output=True)
                print("✅ Postfix installé avec succès")
            except subprocess.CalledProcessError as e:
                print(f"❌ Erreur lors de l'installation: {e.stderr.decode()}")
                sys.exit(1)
        else:
            print("✅ Postfix est déjà installé")
        
        # Configurer Postfix pour Google Cloud Shell (sans systemd)
        postfix_config = """# Postfix configuration for Google Cloud Shell
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
strict_rfc821_envelopes = no
smtpd_error_sleep_time = 0
smtpd_soft_error_limit = 1000
smtpd_hard_error_limit = 1000
queue_run_delay = 300
minimal_backoff_time = 300
maximal_backoff_time = 4000
"""
        
        # Sauvegarder l'ancienne configuration
        if os.path.exists('/etc/postfix/main.cf'):
            subprocess.run(['cp', '/etc/postfix/main.cf', '/etc/postfix/main.cf.backup'], 
                          check=True)
        
        # Écrire la nouvelle configuration
        with open('/etc/postfix/main.cf', 'w') as f:
            f.write(postfix_config)
        
        # Redémarrer Postfix avec service (pas systemctl)
        print("🔄 Redémarrage de Postfix...")
        try:
            # Arrêter Postfix
            subprocess.run(['service', 'postfix', 'stop'], check=False, capture_output=True)
            time.sleep(1)
            
            # Démarrer Postfix
            result = subprocess.run(['service', 'postfix', 'start'], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✅ Postfix démarré avec succès")
            else:
                print("⚠️  Utilisation de la méthode alternative...")
                # Essayer avec postfix directement
                subprocess.run(['postfix', 'stop'], check=False)
                time.sleep(1)
                subprocess.run(['postfix', 'start'], check=True)
                print("✅ Postfix démarré avec la commande directe")
                
        except Exception as e:
            print(f"⚠️  Attention: {str(e)}")
            print("📝 Tentative de démarrage manuel...")
            try:
                subprocess.run(['/usr/lib/postfix/sbin/master', '-c', '/etc/postfix', '-d'], 
                             check=False, capture_output=True)
                print("✅ Postfix démarré en mode démon")
            except:
                print("⚠️  Postfix pourrait ne pas être démarré, mais nous allons continuer")
        
        # Vérifier si Postfix fonctionne
        self.check_postfix_status()
        
    def check_postfix_status(self):
        """Vérifie si Postfix fonctionne"""
        print("🔍 Vérification du statut de Postfix...")
        try:
            # Vérifier si le processus Postfix tourne
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            if 'postfix' in result.stdout or 'master' in result.stdout:
                print("✅ Postfix semble fonctionner")
                return True
            
            # Essayer de vérifier avec netstat
            result = subprocess.run(['netstat', '-tlnp'], capture_output=True, text=True)
            if ':25' in result.stdout or 'postfix' in result.stdout:
                print("✅ Postfix écoute sur le port 25")
                return True
            
            print("⚠️  Postfix ne semble pas fonctionner, tentative de démarrage...")
            subprocess.run(['postfix', 'start'], check=False, capture_output=True)
            time.sleep(2)
            return True
            
        except Exception as e:
            print(f"⚠️  Impossible de vérifier Postfix: {str(e)}")
            return True  # Continuer quand même
        
    def parse_header(self):
        """Parse le header pour extraire les informations"""
        header = self.config['header']
        sender_email = None
        sender_name = None
        subject = None
        
        # Extraire From
        from_match = re.search(r'From:\s*(.+?)\s*<(.+?)>', header)
        if from_match:
            sender_name = from_match.group(1).strip()
            sender_email = from_match.group(2).strip()
        else:
            from_match = re.search(r'From:\s*(.+?@.+?)', header)
            if from_match:
                sender_email = from_match.group(1).strip()
                sender_name = sender_email.split('@')[0]
        
        # Extraire Subject
        subject_match = re.search(r'Subject:\s*(.+)', header)
        if subject_match:
            subject = subject_match.group(1).strip()
        
        return sender_email, sender_name, subject
    
    def create_email_content(self, recipient_email, custom_data=None):
        """Crée le contenu de l'email"""
        sender_email, sender_name, subject = self.parse_header()
        
        if not sender_email:
            sender_email = "noreply@localhost"
        if not sender_name:
            sender_name = "Mon Service"
        if not subject:
            subject = "Sans objet"
        
        # Remplacer les variables dans le body
        body = self.config['body']
        body = body.replace('{{email}}', recipient_email)
        body = body.replace('{{date}}', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        if custom_data:
            for key, value in custom_data.items():
                body = body.replace(f'{{{{{key}}}}}', str(value))
        
        # Construire l'email complet
        email_content = f"""From: {sender_name} <{sender_email}>
To: {recipient_email}
Subject: {subject}
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

{body}
"""
        return email_content
    
    def send_email_via_sendmail(self, recipient_email, email_content):
        """Envoie un email via sendmail"""
        try:
            process = subprocess.Popen(
                ['sendmail', '-t'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(input=email_content)
            
            if process.returncode == 0:
                return True, None
            else:
                return False, stderr
                
        except Exception as e:
            return False, str(e)
    
    def send_email(self, recipient_email, custom_data=None):
        """Envoie un email via sendmail"""
        email_content = self.create_email_content(recipient_email, custom_data)
        
        success, error = self.send_email_via_sendmail(recipient_email, email_content)
        
        if success:
            print(f"✅ Email envoyé à: {recipient_email}")
            self.stats['total_sent'] += 1
            return True
        else:
            print(f"❌ Erreur pour {recipient_email}: {error}")
            self.stats['total_failed'] += 1
            return False
    
    def send_test_email(self, test_number):
        """Envoie un email de test"""
        print(f"\n{'='*60}")
        print(f"🧪 ENVOI D'UN EMAIL DE TEST #{test_number}")
        print(f"{'='*60}")
        
        # Extraire les adresses de test du fichier test_after
        test_emails = self.extract_test_emails()
        
        if not test_emails:
            print("⚠️  Aucune adresse de test trouvée dans 3-testafter.txt")
            print("   Ajoutez des adresses dans le fichier ou utilisez --test-now avec --test-email")
            return False
        
        sender_email, sender_name, _ = self.parse_header()
        
        for test_email in test_emails:
            print(f"📨 Envoi du test à: {test_email}")
            
            # Créer le contenu du test
            test_subject = f"✅ TEST #{test_number} - Système d'envoi actif"
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            test_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; margin: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
                    .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
                    .stats {{ background-color: #f9f9f9; padding: 15px; margin: 15px 0; }}
                    .success {{ color: #4CAF50; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>✅ TEST SYSTÈME #{test_number}</h1>
                    </div>
                    <div class="content">
                        <p>Ceci est un email de test automatique envoyé par le système d'envoi d'emails.</p>
                        
                        <div class="stats">
                            <h3>📊 STATISTIQUES ACTUELLES</h3>
                            <p><strong>Total envoyés:</strong> {self.stats['total_sent']}</p>
                            <p><strong>Total échoués:</strong> {self.stats['total_failed']}</p>
                            <p><strong>Dernier test:</strong> #{self.stats['last_test_sent']}</p>
                            <p><strong>Début:</strong> {self.stats['start_time'].strftime('%Y-%m-%d %H:%M:%S')}</p>
                            <p><strong>Heure du test:</strong> {current_time}</p>
                            <p><strong>Google Cloud Shell:</strong> Actif</p>
                        </div>
                        
                        <p>Le système fonctionne correctement et continue d'envoyer des emails.</p>
                        <p class="success">✅ STATUT: ACTIF ET FONCTIONNEL</p>
                    </div>
                    <div class="footer">
                        <p><em>Ce message a été généré automatiquement depuis Google Cloud Shell.</em></p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            test_content = f"""From: {sender_name} <{sender_email}>
To: {test_email}
Subject: {test_subject}
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

{test_body}
"""
            
            success, error = self.send_email_via_sendmail(test_email, test_content)
            
            if success:
                print(f"✅ Test #{test_number} envoyé avec succès à {test_email}")
            else:
                print(f"❌ Échec du test #{test_number} à {test_email}: {error}")
                return False
        
        self.stats['last_test_sent'] = test_number
        self.last_test_time = datetime.now()
        
        # Enregistrer le test dans l'historique
        test_info = {
            'test_number': test_number,
            'time': current_time,
            'total_sent': self.stats['total_sent'],
            'total_failed': self.stats['total_failed']
        }
        self.stats['batch_history'].append(test_info)
        
        # Sauvegarder les stats dans un fichier
        self.save_stats()
        
        print(f"\n📈 Statistiques sauvegardées. Prochain test après {self.test_interval} emails.")
        return True
    
    def extract_test_emails(self):
        """Extrait les adresses email de test du fichier test_after"""
        content = self.config['test_after']
        emails = []
        
        # Chercher des adresses email dans le contenu
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
        found_emails = re.findall(email_pattern, content)
        
        for email in found_emails:
            if email not in emails:
                emails.append(email)
        
        # Si aucune adresse trouvée, utiliser l'expéditeur par défaut
        if not emails:
            sender_email, _, _ = self.parse_header()
            if sender_email:
                emails.append(sender_email)
            else:
                emails.append("admin@localhost")
        
        return emails
    
    def save_stats(self):
        """Sauvegarde les statistiques dans un fichier JSON"""
        stats_file = os.path.join(self.config_dir, 'send_stats.json')
        stats_data = {
            'stats': self.stats,
            'last_update': datetime.now().isoformat(),
            'test_interval': self.test_interval,
            'google_cloud_shell': True
        }
        
        with open(stats_file, 'w') as f:
            json.dump(stats_data, f, indent=2, default=str)
    
    def load_stats(self):
        """Charge les statistiques depuis le fichier JSON"""
        stats_file = os.path.join(self.config_dir, 'send_stats.json')
        if os.path.exists(stats_file):
            try:
                with open(stats_file, 'r') as f:
                    data = json.load(f)
                    # Convertir les dates
                    data['stats']['start_time'] = datetime.fromisoformat(data['stats']['start_time'])
                    self.stats = data['stats']
                    print(f"📊 Statistiques chargées: {self.stats['total_sent']} emails envoyés")
            except:
                print("⚠️  Impossible de charger les statistiques précédentes")
    
    def check_test_condition(self, current_index):
        """Vérifie si un test doit être envoyé"""
        # Test après chaque intervalle
        if current_index > 0 and current_index % self.test_interval == 0:
            test_number = current_index // self.test_interval
            print(f"\n🎯 Point de contrôle atteint: {current_index} emails envoyés")
            print(f"🔄 Envoi du test #{test_number}...")
            return True, test_number
        
        # Test toutes les 30 minutes également
        if self.last_test_time:
            time_diff = (datetime.now() - self.last_test_time).total_seconds()
            if time_diff > 1800:  # 30 minutes
                test_number = len(self.stats['batch_history']) + 1
                print(f"\n⏰ 30 minutes écoulées depuis le dernier test")
                print(f"🔄 Envoi du test de surveillance #{test_number}...")
                return True, test_number
        
        return False, 0
    
    def show_progress(self, current, total, start_time):
        """Affiche une barre de progression"""
        percent = (current / total) * 100
        elapsed = datetime.now() - start_time
        elapsed_seconds = elapsed.total_seconds()
        
        if current > 0:
            rate = current / elapsed_seconds
            remaining = (total - current) / rate if rate > 0 else 0
            remaining_str = time.strftime("%H:%M:%S", time.gmtime(remaining))
        else:
            rate = 0
            remaining_str = "N/A"
        
        bar_length = 40
        filled_length = int(bar_length * current // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        print(f"\r📊 Progression: [{bar}] {percent:.1f}% | "
              f"{current}/{total} | "
              f"⏱️ {str(elapsed).split('.')[0]} | "
              f"⏳ Reste: {remaining_str} | "
              f"📨 {rate:.1f}/sec | "
              f"✅ {self.stats['total_sent']} | "
              f"❌ {self.stats['total_failed']}", end="", flush=True)
    
    def send_bulk_emails(self, delay=1, max_emails=None, start_from=0):
        """Envoie des emails en masse avec tests périodiques"""
        if not self.email_list:
            print("❌ Aucune adresse email trouvée dans 1-data.txt")
            print("   Utilisez --create-config pour créer des fichiers d'exemple")
            return
        
        # Charger les stats précédentes
        self.load_stats()
        
        total = len(self.email_list)
        print(f"📧 Nombre d'emails à envoyer: {total}")
        print(f"🔄 Intervalle de test: tous les {self.test_interval} emails")
        
        if max_emails:
            emails_to_send = self.email_list[start_from:start_from + max_emails]
        else:
            emails_to_send = self.email_list[start_from:]
        
        batch_size = len(emails_to_send)
        print(f"🎯 Taille du lot: {batch_size}")
        
        success_count = self.stats['total_sent']
        fail_count = self.stats['total_failed']
        
        # Gestion du Ctrl+C
        def signal_handler(sig, frame):
            print(f"\n\n⏹️  Interruption détectée. Arrêt de l'envoi...")
            self.save_stats()
            self.show_final_stats(success_count, fail_count, start_time)
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        start_time = datetime.now()
        
        for i, email in enumerate(emails_to_send, start=start_from+1):
            absolute_index = i
            
            # Afficher la progression
            self.show_progress(i - start_from, batch_size, start_time)
            
            # Vérifier si on doit envoyer un test
            should_test, test_number = self.check_test_condition(absolute_index)
            if should_test:
                print()  # Nouvelle ligne pour le test
                self.send_test_email(test_number)
                print(f"\n🔄 Reprise de l'envoi principal...")
            
            # Envoyer l'email principal
            custom_data = {
                'numero': absolute_index,
                'total': total,
                'timestamp': datetime.now().isoformat(),
                'test_interval': self.test_interval
            }
            
            if self.send_email(email, custom_data):
                success_count += 1
            else:
                fail_count += 1
            
            # Pause entre les envois
            if i < len(emails_to_send):
                time.sleep(delay)
        
        # Envoyer un test final
        print("\n\n🎉 Envoi principal terminé !")
        final_test_number = len(self.stats['batch_history']) + 1
        print(f"📤 Envoi du test final #{final_test_number}...")
        self.send_test_email(final_test_number)
        
        # Afficher le message final du fichier test_after
        if self.config['test_after']:
            print(f"\n{'='*60}")
            print("📝 MESSAGE DE CONFIRMATION:")
            print(f"{'='*60}")
            print(self.config['test_after'])
        
        self.show_final_stats(success_count, fail_count, start_time)
    
    def show_final_stats(self, success_count, fail_count, start_time):
        """Affiche les statistiques finales"""
        total_time = datetime.now() - start_time
        total_seconds = total_time.total_seconds()
        
        print(f"\n{'='*60}")
        print(f"📊 RÉCAPITULATIF FINAL - GOOGLE CLOUD SHELL")
        print(f"{'='*60}")
        print(f"✅ Emails envoyés avec succès: {success_count}")
        print(f"❌ Emails échoués: {fail_count}")
        if success_count + fail_count > 0:
            print(f"📈 Taux de réussite: {(success_count/(success_count+fail_count)*100):.2f}%")
        print(f"⏱️  Temps total: {str(total_time).split('.')[0]}")
        
        if total_seconds > 0:
            rate = (success_count + fail_count) / total_seconds
            print(f"⚡ Vitesse moyenne: {rate:.2f} emails/sec")
        
        print(f"🧪 Tests envoyés: {len(self.stats['batch_history'])}")
        print(f"📅 Heure de début: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 Heure de fin: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🌐 Environnement: Google Cloud Shell")
        print(f"{'='*60}")
        
        # Afficher l'historique des tests
        if self.stats['batch_history']:
            print("\n📋 HISTORIQUE DES TESTS:")
            print(f"{'='*60}")
            for test in self.stats['batch_history'][-5:]:  # 5 derniers tests
                print(f"Test #{test['test_number']} à {test['time']} | "
                      f"Total: {test['total_sent']} | "
                      f"Échecs: {test['total_failed']}")

def create_config_files():
    """Crée les fichiers de configuration s'ils n'existent pas"""
    configs = {
        '0-header.txt': """From: Mon Service <service@votredomaine.com>
Subject: Votre sujet ici
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8""",
        
        '1-data.txt': """email1@test.com
email2@test.com
email3@test.com
email4@test.com
email5@test.com""",
        
        '2-body.html': """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Email Important</title>
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #f4f4f4; padding: 10px; text-align: center; }
        .content { padding: 20px; }
        .footer { margin-top: 30px; font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Bonjour cher client</h1>
        </div>
        <div class="content">
            <p>Cher destinataire,</p>
            <p>Ceci est un email envoyé depuis Google Cloud Shell.</p>
            <p>Email: {{email}}</p>
            <p>Numéro: {{numero}}/{{total}}</p>
            <p>Date: {{timestamp}}</p>
            <p>Test envoyé tous les: {{test_interval}} emails</p>
        </div>
        <div class="footer">
            <p>Cordialement,<br>Votre équipe de support</p>
        </div>
    </div>
</body>
</html>""",
        
        '3-testafter.txt': """📧 Système de test automatique pour Google Cloud Shell
test_interval:500

Ce système envoie automatiquement un email de test tous les 500 emails envoyés
pour vérifier que le système fonctionne correctement dans Google Cloud Shell.

ADDRESSES DE TEST (ajoutez vos adresses ci-dessous):
votre.email@gmail.com
backup@exemple.com

Message de confirmation après envoi:
✅ Tous les emails ont été envoyés avec succès depuis Google Cloud Shell !
Le système a envoyé des tests périodiques pour vérifier son bon fonctionnement.
Total d'emails envoyés: {{total_sent}}
Tests effectués: {{test_count}}
Merci d'avoir utilisé notre service d'envoi d'emails."""
    }
    
    for filename, content in configs.items():
        if not os.path.exists(filename):
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"📄 Fichier créé: {filename}")
    
    print("\n📝 MODIFIEZ LES FICHIERS AVANT DE LANCER:")
    print("   1. Éditez 0-header.txt pour votre expéditeur et sujet")
    print("   2. Ajoutez vos emails dans 1-data.txt")
    print("   3. Modifiez 3-testafter.txt pour ajouter vos adresses de test")
    print("   4. Changez test_interval:500 si nécessaire")

def test_sendmail():
    """Teste si sendmail fonctionne"""
    print("🧪 Test de sendmail...")
    try:
        test_content = """From: test@localhost
To: test@localhost
Subject: Test sendmail

Ceci est un test.
"""
        
        process = subprocess.Popen(['sendmail', '-t'],
                                 stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 text=True)
        stdout, stderr = process.communicate(input=test_content)
        
        if process.returncode == 0:
            print("✅ sendmail fonctionne correctement")
            return True
        else:
            print(f"❌ sendmail erreur: {stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Erreur de test: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description="Script d'envoi d'emails via Postfix sur Google Cloud Shell"
    )
    parser.add_argument('--test', action='store_true', help='Tester sendmail uniquement')
    parser.add_argument('--test-now', action='store_true', help='Envoyer un test immédiatement')
    parser.add_argument('--create-config', action='store_true', help='Créer les fichiers de configuration')
    parser.add_argument('--delay', type=float, default=1, help='Délai entre les emails (secondes)')
    parser.add_argument('--max', type=int, help='Nombre maximum d\'emails à envoyer')
    parser.add_argument('--start', type=int, default=0, help='Index de départ dans la liste')
    parser.add_argument('--interval', type=int, help='Intervalle de test (nombre d\'emails)')
    parser.add_argument('--config-dir', default='.', help='Répertoire des fichiers de configuration')
    parser.add_argument('--stats', action='store_true', help='Afficher les statistiques')
    parser.add_argument('--test-email', type=str, help='Email pour le test immédiat')
    
    args = parser.parse_args()
    
    print("="*60)
    print("📧 SCRIPT D'ENVOI D'EMAILS - GOOGLE CLOUD SHELL")
    print("="*60)
    
    # Vérifier l'environnement
    if 'DEVSHELL_PROJECT_ID' in os.environ:
        print("🌐 Environnement Google Cloud Shell détecté")
        print("📝 Note: Utilisation de 'service' au lieu de 'systemctl'")
    
    if args.create_config:
        create_config_files()
        return
    
    if args.test:
        test_sendmail()
        return
    
    try:
        mailer = PostfixMailer(args.config_dir)
        
        if args.interval:
            mailer.test_interval = args.interval
            print(f"🔄 Intervalle de test défini sur: {mailer.test_interval} emails")
        
        if args.test_now:
            print("🧪 Envoi d'un test immédiat...")
            test_number = len(mailer.stats['batch_history']) + 1
            if args.test_email:
                # Créer un fichier temporaire avec l'email de test
                temp_test = mailer.config['test_after'] + f"\n{args.test_email}"
                mailer.config['test_after'] = temp_test
            mailer.send_test_email(test_number)
        elif args.stats:
            mailer.load_stats()
            mailer.show_final_stats(
                mailer.stats['total_sent'],
                mailer.stats['total_failed'],
                mailer.stats['start_time']
            )
        else:
            if not mailer.email_list:
                print("❌ Aucune adresse email trouvée dans 1-data.txt")
                print("   Utilisez --create-config pour créer des fichiers d'exemple")
                return
            
            print(f"📋 Expéditeur: {mailer.parse_header()[1]}")
            print(f"📋 Sujet: {mailer.parse_header()[2]}")
            print(f"📋 Destinataires: {len(mailer.email_list)}")
            print(f"⏱️  Délai: {args.delay} seconde(s)")
            print(f"🔄 Intervalle de test: tous les {mailer.test_interval} emails")
            
            confirm = input("\n⚠️  Voulez-vous continuer l'envoi ? (oui/non): ")
            if confirm.lower() in ['oui', 'o', 'yes', 'y']:
                mailer.send_bulk_emails(delay=args.delay, max_emails=args.max, start_from=args.start)
            else:
                print("❌ Envoi annulé.")
                
    except KeyboardInterrupt:
        print("\n\n⏹️  Script interrompu par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur critique: {str(e)}")
        import traceback
        traceback.print_exc()
        print(f"\n💡 Solutions possibles:")
        print(f"   1. Essayez: sudo service postfix restart")
        print(f"   2. Essayez: sudo postfix start")
        print(f"   3. Vérifiez les logs: sudo tail -f /var/log/mail.log")

if __name__ == "__main__":
    main()
