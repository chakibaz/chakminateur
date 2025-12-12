#!/usr/bin/env python3
"""
Script d'envoi d'emails intelligent pour Google Cloud Shell
Avec gestion de pause, rotation, templates multiples et reprise automatique
Auteur: Expert IA
Usage: python3 send.py
"""

import os
import sys
import subprocess
import time
import re
import json
import random
import hashlib
import pickle
from datetime import datetime, timedelta
import signal
import argparse
import shutil
from pathlib import Path
import sqlite3
from typing import List, Dict, Tuple, Optional
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_sender.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EmailManager:
    """Gestionnaire intelligent d'envoi d'emails"""
    
    def __init__(self, config_dir="config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        # Initialiser les bases de données
        self.init_databases()
        
        # Charger la configuration
        self.load_configuration()
        
        # Configurer Postfix
        self.setup_postfix()
        
        # Variables d'état
        self.current_session = None
        self.pause_after = 100  # Pause après 100 emails par défaut
        self.pause_duration = 300  # 5 minutes par défaut
        
    def init_databases(self):
        """Initialiser les bases de données SQLite"""
        # Base de données principale
        self.db_path = self.config_dir / "email_manager.db"
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
        # Créer les tables si elles n'existent pas
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time DATETIME,
                end_time DATETIME,
                total_emails INTEGER,
                sent_emails INTEGER,
                failed_emails INTEGER,
                status TEXT,
                config_hash TEXT
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                email_address TEXT,
                template_id INTEGER,
                subject_id INTEGER,
                from_id INTEGER,
                send_time DATETIME,
                status TEXT,
                error_message TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS templates (
                template_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                content TEXT,
                is_active BOOLEAN DEFAULT 1,
                weight INTEGER DEFAULT 1
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_text TEXT,
                is_active BOOLEAN DEFAULT 1,
                weight INTEGER DEFAULT 1
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS from_lines (
                from_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                email TEXT,
                is_active BOOLEAN DEFAULT 1,
                weight INTEGER DEFAULT 1
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS email_lists (
                list_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                file_path TEXT,
                total_emails INTEGER,
                last_position INTEGER DEFAULT 0
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS rotation_rules (
                rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                rule_type TEXT,
                value INTEGER,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        self.conn.commit()
        
    def load_configuration(self):
        """Charger la configuration depuis les fichiers"""
        # Créer la structure de dossiers si nécessaire
        (self.config_dir / "templates").mkdir(exist_ok=True)
        (self.config_dir / "email_lists").mkdir(exist_ok=True)
        
        # Charger la configuration générale
        self.config = self.load_json_config("config.json", {
            "pause_after": 100,
            "pause_duration": 300,
            "test_interval": 50,
            "delay_between_emails": 1,
            "max_emails_per_session": 1000,
            "rotation_mode": "random",  # random, sequential, weighted
            "enable_test_emails": True,
            "test_email_recipients": [],
            "postfix_config": {
                "myhostname": "localhost",
                "inet_interfaces": "loopback-only"
            }
        })
        
        # Mettre à jour les variables
        self.pause_after = self.config["pause_after"]
        self.pause_duration = self.config["pause_duration"]
        
        # Charger les templates
        self.load_templates()
        
        # Charger les sujets
        self.load_subjects()
        
        # Charger les from lines
        self.load_from_lines()
        
        # Charger les listes d'emails
        self.load_email_lists()
        
        # Charger les règles de rotation
        self.load_rotation_rules()
        
    def load_json_config(self, filename: str, default_config: dict) -> dict:
        """Charger un fichier JSON ou créer avec des valeurs par défaut"""
        filepath = self.config_dir / filename
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2)
            return default_config
        
    def load_templates(self):
        """Charger les templates depuis la base de données et les fichiers"""
        # Vérifier s'il y a des templates dans la base
        self.cursor.execute("SELECT COUNT(*) FROM templates WHERE is_active = 1")
        count = self.cursor.fetchone()[0]
        
        if count == 0:
            # Créer des templates par défaut
            default_templates = [
                ("Template 1", self.get_default_template(1), 1),
                ("Template 2", self.get_default_template(2), 1),
                ("Template 3", self.get_default_template(3), 1)
            ]
            
            for name, content, weight in default_templates:
                self.cursor.execute(
                    "INSERT INTO templates (name, content, weight) VALUES (?, ?, ?)",
                    (name, content, weight)
                )
            
            self.conn.commit()
        
        # Charger les templates actifs
        self.cursor.execute(
            "SELECT template_id, name, content, weight FROM templates WHERE is_active = 1"
        )
        self.templates = [
            {
                'id': row[0],
                'name': row[1],
                'content': row[2],
                'weight': row[3]
            }
            for row in self.cursor.fetchall()
        ]
        
    def get_default_template(self, number: int) -> str:
        """Retourner un template par défaut"""
        templates = [
            """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Email Important</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h1 style="color: #333;">Message Important</h1>
        <p>Cher destinataire,</p>
        <p>Ceci est notre premier template d'email.</p>
        <p>Email: {{email}}</p>
        <p>Date: {{timestamp}}</p>
        <p>Template: {{template_name}}</p>
        <p><strong>Ceci est un message important pour vous.</strong></p>
        <p>Cordialement,<br>L'équipe de support</p>
    </div>
</body>
</html>""",
            """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Nouvelle Offre</title>
</head>
<body style="font-family: Georgia, serif; line-height: 1.8;">
    <div style="max-width: 600px; margin: 0 auto; padding: 30px; background-color: #f9f9f9;">
        <div style="text-align: center; margin-bottom: 30px;">
            <h2 style="color: #2c3e50;">OFFRE SPÉCIALE</h2>
        </div>
        <p>Bonjour,</p>
        <p>Nous avons une offre spéciale qui pourrait vous intéresser.</p>
        <div style="background-color: #fff; padding: 20px; border-left: 4px solid #3498db; margin: 20px 0;">
            <p><strong>Détails de l'offre:</strong></p>
            <p>• Email: {{email}}</p>
            <p>• Heure: {{timestamp}}</p>
            <p>• Référence: {{template_name}}</p>
        </div>
        <p>Ne manquez pas cette opportunité !</p>
        <p>Bien à vous,<br>L'équipe commerciale</p>
    </div>
</body>
</html>""",
            """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Newsletter</title>
</head>
<body style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;">
    <div style="max-width: 600px; margin: 0 auto; border: 1px solid #ddd;">
        <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center;">
            <h1>NEWSLETTER</h1>
        </div>
        <div style="padding: 30px;">
            <p>Salut !</p>
            <p>Voici les dernières nouvelles de notre newsletter.</p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px;"><strong>Destinataire</strong></td>
                    <td style="border: 1px solid #ddd; padding: 10px;">{{email}}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px;"><strong>Date</strong></td>
                    <td style="border: 1px solid #ddd; padding: 10px;">{{timestamp}}</td>
                </tr>
                <tr>
                    <td style="border: 1px solid #ddd; padding: 10px;"><strong>Template</strong></td>
                    <td style="border: 1px solid #ddd; padding: 10px;">{{template_name}}</td>
                </tr>
            </table>
            <p>Restez connecté pour plus d'actualités !</p>
            <p>À bientôt,<br>L'équipe communication</p>
        </div>
    </div>
</body>
</html>"""
        ]
        
        return templates[number - 1] if 1 <= number <= 3 else templates[0]
        
    def load_subjects(self):
        """Charger les sujets depuis la base de données"""
        self.cursor.execute(
            "SELECT subject_id, subject_text, weight FROM subjects WHERE is_active = 1"
        )
        self.subjects = [
            {
                'id': row[0],
                'text': row[1],
                'weight': row[2]
            }
            for row in self.cursor.fetchall()
        ]
        
        if not self.subjects:
            # Créer des sujets par défaut
            default_subjects = [
                ("Message important de notre équipe", 1),
                ("Nouvelle offre spéciale pour vous", 1),
                ("Votre newsletter mensuelle", 1),
                ("Mise à jour importante", 1),
                ("Opportunité exclusive", 1)
            ]
            
            for text, weight in default_subjects:
                self.cursor.execute(
                    "INSERT INTO subjects (subject_text, weight) VALUES (?, ?)",
                    (text, weight)
                )
            
            self.conn.commit()
            self.load_subjects()  # Recharger
        
    def load_from_lines(self):
        """Charger les from lines depuis la base de données"""
        self.cursor.execute(
            "SELECT from_id, name, email, weight FROM from_lines WHERE is_active = 1"
        )
        self.from_lines = [
            {
                'id': row[0],
                'name': row[1],
                'email': row[2],
                'weight': row[3]
            }
            for row in self.cursor.fetchall()
        ]
        
        if not self.from_lines:
            # Créer des from lines par défaut
            default_froms = [
                ("Support Technique", "support@example.com", 1),
                ("Équipe Commerciale", "commercial@example.com", 1),
                ("Service Clients", "client@example.com", 1),
                ("Administration", "admin@example.com", 1)
            ]
            
            for name, email, weight in default_froms:
                self.cursor.execute(
                    "INSERT INTO from_lines (name, email, weight) VALUES (?, ?, ?)",
                    (name, email, weight)
                )
            
            self.conn.commit()
            self.load_from_lines()  # Recharger
        
    def load_email_lists(self):
        """Charger les listes d'emails"""
        self.cursor.execute("SELECT list_id, name, file_path, last_position FROM email_lists")
        self.email_lists = [
            {
                'id': row[0],
                'name': row[1],
                'file_path': row[2],
                'last_position': row[3]
            }
            for row in self.cursor.fetchall()
        ]
        
    def load_rotation_rules(self):
        """Charger les règles de rotation"""
        self.cursor.execute("SELECT rule_type, value FROM rotation_rules WHERE is_active = 1")
        self.rotation_rules = {row[0]: row[1] for row in self.cursor.fetchall()}
        
    def setup_postfix(self):
        """Configurer Postfix pour Google Cloud Shell"""
        logger.info("Configuration de Postfix pour Google Cloud Shell...")
        
        # Vérifier les privilèges
        if os.geteuid() != 0:
            logger.error("Ce script nécessite des privilèges sudo.")
            logger.error("Veuillez exécuter: sudo python3 send.py")
            sys.exit(1)
        
        # Vérifier si Postfix est déjà installé
        if shutil.which('postfix') is None:
            logger.info("Installation de Postfix et dépendances...")
            try:
                subprocess.run(['apt-get', 'update', '-y'], check=True, capture_output=True)
                subprocess.run(['apt-get', 'install', '-y', 'postfix', 'mailutils'], 
                             check=True, capture_output=True)
                logger.info("Postfix installé avec succès")
            except subprocess.CalledProcessError as e:
                logger.error(f"Erreur lors de l'installation: {e.stderr.decode()}")
                sys.exit(1)
        else:
            logger.info("Postfix est déjà installé")
        
        # Configurer Postfix
        postfix_config = f"""# Postfix configuration for Google Cloud Shell
myhostname = {self.config['postfix_config']['myhostname']}
inet_interfaces = {self.config['postfix_config']['inet_interfaces']}
inet_protocols = all
relayhost = 
mydestination = localhost
smtp_sasl_auth_enable = no
smtpd_sasl_auth_enable = no
smtp_tls_security_level = none
mailbox_size_limit = 0
recipient_delimiter = +
disable_vrfy_command = yes
"""
        
        # Sauvegarder l'ancienne configuration
        if os.path.exists('/etc/postfix/main.cf'):
            subprocess.run(['cp', '/etc/postfix/main.cf', '/etc/postfix/main.cf.backup'], 
                          check=True)
        
        # Écrire la nouvelle configuration
        with open('/etc/postfix/main.cf', 'w') as f:
            f.write(postfix_config)
        
        # Redémarrer Postfix
        self.restart_postfix()
        
    def restart_postfix(self):
        """Redémarrer Postfix"""
        logger.info("Redémarrage de Postfix...")
        try:
            # Essayer avec service
            subprocess.run(['service', 'postfix', 'restart'], 
                          capture_output=True, text=True, check=False)
            
            # Vérifier si Postfix tourne
            time.sleep(2)
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
            if 'postfix' in result.stdout or 'master' in result.stdout:
                logger.info("✅ Postfix démarré avec succès")
            else:
                # Essayer avec postfix directement
                subprocess.run(['postfix', 'stop'], check=False)
                time.sleep(1)
                subprocess.run(['postfix', 'start'], check=True)
                logger.info("✅ Postfix démarré avec la commande directe")
                
        except Exception as e:
            logger.warning(f"Attention lors du redémarrage: {str(e)}")
            logger.info("Tentative de poursuite sans redémarrage...")
        
    def select_random_item(self, items: List[Dict]) -> Dict:
        """Sélectionner un item aléatoire avec prise en compte des poids"""
        if not items:
            return None
            
        # Si rotation_mode est weighted
        if self.config.get("rotation_mode") == "weighted":
            total_weight = sum(item.get('weight', 1) for item in items)
            rand = random.uniform(0, total_weight)
            current = 0
            for item in items:
                current += item.get('weight', 1)
                if rand <= current:
                    return item
        
        # Mode random simple
        return random.choice(items)
        
    def get_next_combination(self) -> Tuple[Dict, Dict, Dict]:
        """Obtenir la prochaine combinaison template/sujet/from"""
        template = self.select_random_item(self.templates)
        subject = self.select_random_item(self.subjects)
        from_line = self.select_random_item(self.from_lines)
        
        return template, subject, from_line
        
    def create_email_content(self, recipient: str, template: Dict, 
                           subject: Dict, from_line: Dict, 
                           custom_data: Dict = None) -> str:
        """Créer le contenu de l'email"""
        # Remplacer les variables dans le template
        content = template['content']
        
        replacements = {
            '{{email}}': recipient,
            '{{timestamp}}': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            '{{template_name}}': template['name'],
            '{{subject_text}}': subject['text'],
            '{{from_name}}': from_line['name'],
            '{{from_email}}': from_line['email']
        }
        
        if custom_data:
            for key, value in custom_data.items():
                replacements[f'{{{{{key}}}}}'] = str(value)
        
        for key, value in replacements.items():
            content = content.replace(key, value)
        
        # Construire l'email complet
        email_content = f"""From: {from_line['name']} <{from_line['email']}>
To: {recipient}
Subject: {subject['text']}
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

{content}
"""
        return email_content
        
    def send_email(self, recipient: str, template: Dict, 
                  subject: Dict, from_line: Dict,
                  session_id: str) -> bool:
        """Envoyer un email via sendmail"""
        email_content = self.create_email_content(recipient, template, subject, from_line)
        
        try:
            process = subprocess.Popen(
                ['sendmail', '-t'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            stdout, stderr = process.communicate(input=email_content)
            
            status = "SUCCESS" if process.returncode == 0 else "FAILED"
            error_msg = stderr if process.returncode != 0 else None
            
            # Log dans la base de données
            self.cursor.execute('''
                INSERT INTO email_logs 
                (session_id, email_address, template_id, subject_id, from_id, send_time, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, recipient, template['id'], subject['id'], 
                  from_line['id'], datetime.now(), status, error_msg))
            
            self.conn.commit()
            
            if status == "SUCCESS":
                logger.info(f"✅ Email envoyé à: {recipient}")
                logger.debug(f"  Template: {template['name']}")
                logger.debug(f"  Sujet: {subject['text']}")
                logger.debug(f"  De: {from_line['name']} <{from_line['email']}>")
                return True
            else:
                logger.error(f"❌ Erreur pour {recipient}: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception pour {recipient}: {str(e)}")
            
            self.cursor.execute('''
                INSERT INTO email_logs 
                (session_id, email_address, template_id, subject_id, from_id, send_time, status, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, recipient, template['id'], subject['id'], 
                  from_line['id'], datetime.now(), "FAILED", str(e)))
            
            self.conn.commit()
            return False
            
    def start_session(self, list_id: int = None, list_name: str = None) -> str:
        """Démarrer une nouvelle session d'envoi"""
        session_id = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]
        
        # Déterminer la liste d'emails
        if list_id:
            email_list = next((lst for lst in self.email_lists if lst['id'] == list_id), None)
        elif list_name:
            email_list = next((lst for lst in self.email_lists if lst['name'] == list_name), None)
        else:
            # Utiliser la première liste disponible
            email_list = self.email_lists[0] if self.email_lists else None
            
        if not email_list:
            logger.error("Aucune liste d'emails disponible")
            return None
            
        # Calculer le hash de configuration
        config_hash = self.calculate_config_hash()
        
        # Enregistrer la session
        self.cursor.execute('''
            INSERT INTO sessions 
            (session_id, start_time, total_emails, sent_emails, failed_emails, status, config_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, datetime.now(), 0, 0, 0, "STARTED", config_hash))
        
        self.conn.commit()
        self.current_session = session_id
        
        logger.info(f"🎬 Début de la session: {session_id}")
        logger.info(f"📋 Liste: {email_list['name']}")
        logger.info(f"📍 Position de reprise: {email_list['last_position']}")
        
        return session_id
        
    def calculate_config_hash(self) -> str:
        """Calculer un hash de la configuration actuelle"""
        config_data = {
            'templates': [(t['id'], t['name']) for t in self.templates],
            'subjects': [(s['id'], s['text']) for s in self.subjects],
            'from_lines': [(f['id'], f['name']) for f in self.from_lines],
            'config': self.config
        }
        
        return hashlib.md5(json.dumps(config_data, sort_keys=True).encode()).hexdigest()
        
    def get_emails_from_list(self, list_id: int, start_position: int = 0, 
                           limit: int = None) -> List[str]:
        """Obtenir des emails depuis une liste"""
        email_list = next((lst for lst in self.email_lists if lst['id'] == list_id), None)
        if not email_list:
            return []
            
        filepath = Path(email_list['file_path'])
        if not filepath.exists():
            logger.error(f"Fichier non trouvé: {filepath}")
            return []
            
        emails = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i < start_position:
                    continue
                    
                email = line.strip()
                if email and '@' in email:
                    emails.append(email)
                    
                if limit and len(emails) >= limit:
                    break
                    
        return emails
        
    def update_list_position(self, list_id: int, position: int):
        """Mettre à jour la position dans la liste"""
        self.cursor.execute(
            "UPDATE email_lists SET last_position = ? WHERE list_id = ?",
            (position, list_id)
        )
        self.conn.commit()
        
    def send_bulk_emails(self, list_id: int = None, max_emails: int = None, 
                        resume: bool = True):
        """Envoyer des emails en masse avec gestion intelligente"""
        # Démarrer une session
        session_id = self.start_session(list_id)
        if not session_id:
            return
            
        # Obtenir la liste d'emails
        email_list = next((lst for lst in self.email_lists if lst['id'] == list_id), None)
        if not email_list:
            logger.error("Liste d'emails non trouvée")
            return
            
        # Déterminer la position de départ
        start_position = email_list['last_position'] if resume else 0
        
        # Obtenir les emails
        emails = self.get_emails_from_list(list_id, start_position, max_emails)
        total_emails = len(emails)
        
        if total_emails == 0:
            logger.warning("Aucun email à envoyer")
            return
            
        logger.info(f"📧 Emails à envoyer: {total_emails}")
        logger.info(f"📍 Début à la position: {start_position}")
        logger.info(f"⏸️  Pause après: {self.pause_after} emails")
        logger.info(f"⏱️  Durée de pause: {self.pause_duration} secondes")
        
        sent_count = 0
        failed_count = 0
        current_position = start_position
        
        # Gestion du Ctrl+C
        def signal_handler(sig, frame):
            logger.info("\n\n⏹️  Interruption détectée. Sauvegarde de l'état...")
            self.update_list_position(list_id, current_position)
            self.update_session_stats(session_id, sent_count, failed_count, "INTERRUPTED")
            self.show_session_stats(session_id)
            sys.exit(0)
            
        signal.signal(signal.SIGINT, signal_handler)
        
        start_time = datetime.now()
        
        for i, email in enumerate(emails):
            current_position = start_position + i + 1
            
            # Afficher la progression
            self.show_progress(i, total_emails, sent_count, failed_count, start_time)
            
            # Sélectionner la combinaison aléatoire
            template, subject, from_line = self.get_next_combination()
            
            # Envoyer l'email
            if self.send_email(email, template, subject, from_line, session_id):
                sent_count += 1
            else:
                failed_count += 1
            
            # Mettre à jour les stats de session
            if (i + 1) % 10 == 0:  # Tous les 10 emails
                self.update_session_stats(session_id, sent_count, failed_count, "RUNNING")
            
            # Vérifier si on doit faire une pause
            if self.pause_after > 0 and (i + 1) % self.pause_after == 0 and (i + 1) < total_emails:
                logger.info(f"\n⏸️  Pause après {i + 1} emails...")
                logger.info(f"😴 Reprise dans {self.pause_duration} secondes")
                
                # Envoyer un email de test si configuré
                if self.config.get("enable_test_emails") and self.config.get("test_email_recipients"):
                    self.send_test_email(session_id, sent_count, failed_count)
                
                # Attendre
                for remaining in range(self.pause_duration, 0, -1):
                    print(f"\r⏳ Reprise dans {remaining} secondes...", end="", flush=True)
                    time.sleep(1)
                print()
                
                logger.info("🔄 Reprise de l'envoi...")
            
            # Pause entre les emails
            time.sleep(self.config.get("delay_between_emails", 1))
        
        # Finaliser la session
        self.update_list_position(list_id, current_position)
        self.update_session_stats(session_id, sent_count, failed_count, "COMPLETED")
        
        # Envoyer un email de test final
        if self.config.get("enable_test_emails") and self.config.get("test_email_recipients"):
            self.send_test_email(session_id, sent_count, failed_count, is_final=True)
        
        # Afficher les stats finales
        self.show_session_stats(session_id)
        
    def show_progress(self, current: int, total: int, sent: int, 
                     failed: int, start_time: datetime):
        """Afficher une barre de progression"""
        percent = (current / total) * 100 if total > 0 else 0
        elapsed = datetime.now() - start_time
        elapsed_seconds = elapsed.total_seconds()
        
        if current > 0:
            rate = current / elapsed_seconds
            remaining = (total - current) / rate if rate > 0 else 0
            remaining_str = str(timedelta(seconds=int(remaining)))
        else:
            rate = 0
            remaining_str = "N/A"
        
        bar_length = 40
        filled_length = int(bar_length * current // total)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        print(f"\r📊 [{bar}] {percent:.1f}% | "
              f"📨 {current}/{total} | "
              f"⏱️ {str(elapsed).split('.')[0]} | "
              f"⏳ {remaining_str} | "
              f"⚡ {rate:.1f}/sec | "
              f"✅ {sent} | "
              f"❌ {failed}", end="", flush=True)
        
    def update_session_stats(self, session_id: str, sent: int, 
                           failed: int, status: str):
        """Mettre à jour les statistiques de session"""
        self.cursor.execute('''
            UPDATE sessions 
            SET sent_emails = ?, failed_emails = ?, status = ?, end_time = ?
            WHERE session_id = ?
        ''', (sent, failed, status, datetime.now(), session_id))
        self.conn.commit()
        
    def show_session_stats(self, session_id: str):
        """Afficher les statistiques de session"""
        self.cursor.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )
        session = self.cursor.fetchone()
        
        if not session:
            return
            
        print(f"\n{'='*60}")
        print("📊 STATISTIQUES DE SESSION")
        print(f"{'='*60}")
        print(f"Session ID: {session[0]}")
        print(f"Début: {session[1]}")
        print(f"Fin: {session[2] if session[2] else 'En cours'}")
        print(f"Total emails: {session[3]}")
        print(f"✅ Envoyés: {session[4]}")
        print(f"❌ Échoués: {session[5]}")
        print(f"Statut: {session[6]}")
        print(f"{'='*60}")
        
    def send_test_email(self, session_id: str, sent: int, failed: int, 
                       is_final: bool = False):
        """Envoyer un email de test"""
        if not self.config.get("test_email_recipients"):
            return
            
        test_recipients = self.config["test_email_recipients"]
        
        for recipient in test_recipients:
            template, subject, from_line = self.get_next_combination()
            
            # Créer un contenu spécial pour le test
            test_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background-color: {'#4CAF50' if not is_final else '#2196F3'}; 
                  color: white; padding: 15px; text-align: center; }}
        .stats {{ background-color: #f5f5f5; padding: 15px; margin: 15px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>{'✅ TEST PÉRIODIQUE' if not is_final else '🎉 ENVOI TERMINÉ'}</h2>
        </div>
        <p>Ceci est un email de test automatique.</p>
        
        <div class="stats">
            <h3>📊 STATISTIQUES</h3>
            <p><strong>Session:</strong> {session_id}</p>
            <p><strong>Type:</strong> {'Test périodique' if not is_final else 'Test final'}</p>
            <p><strong>Heure:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>Emails envoyés:</strong> {sent}</p>
            <p><strong>Emails échoués:</strong> {failed}</p>
            <p><strong>Taux de réussite:</strong> {(sent/(sent+failed)*100 if sent+failed>0 else 0):.1f}%</p>
        </div>
        
        <p>Le système fonctionne correctement.</p>
        <p><em>Message généré automatiquement</em></p>
    </div>
</body>
</html>"""
            
            # Créer l'email
            test_subject = f"{'[TEST] ' if not is_final else '[FIN] '}Système d'envoi - Session {session_id}"
            
            email_content = f"""From: {from_line['name']} <{from_line['email']}>
To: {recipient}
Subject: {test_subject}
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

{test_content}
"""
            
            # Envoyer l'email
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
                    logger.info(f"✅ Email de test envoyé à: {recipient}")
                else:
                    logger.error(f"❌ Échec du test à {recipient}: {stderr}")
                    
            except Exception as e:
                logger.error(f"❌ Exception lors du test: {str(e)}")
                
    def add_email_list(self, name: str, file_path: str):
        """Ajouter une liste d'emails"""
        # Compter les emails dans le fichier
        count = 0
        if Path(file_path).exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip() and '@' in line.strip():
                        count += 1
        
        self.cursor.execute('''
            INSERT INTO email_lists (name, file_path, total_emails)
            VALUES (?, ?, ?)
        ''', (name, file_path, count))
        
        self.conn.commit()
        self.load_email_lists()  # Recharger
        
        logger.info(f"✅ Liste ajoutée: {name} ({count} emails)")
        
    def add_template(self, name: str, content: str, weight: int = 1):
        """Ajouter un template"""
        self.cursor.execute('''
            INSERT INTO templates (name, content, weight)
            VALUES (?, ?, ?)
        ''', (name, content, weight))
        
        self.conn.commit()
        self.load_templates()  # Recharger
        
        logger.info(f"✅ Template ajouté: {name}")
        
    def add_subject(self, text: str, weight: int = 1):
        """Ajouter un sujet"""
        self.cursor.execute('''
            INSERT INTO subjects (subject_text, weight)
            VALUES (?, ?)
        ''', (text, weight))
        
        self.conn.commit()
        self.load_subjects()  # Recharger
        
        logger.info(f"✅ Sujet ajouté: {text}")
        
    def add_from_line(self, name: str, email: str, weight: int = 1):
        """Ajouter une from line"""
        self.cursor.execute('''
            INSERT INTO from_lines (name, email, weight)
            VALUES (?, ?, ?)
        ''', (name, email, weight))
        
        self.conn.commit()
        self.load_from_lines()  # Recharger
        
        logger.info(f"✅ From line ajouté: {name} <{email}>")
        
    def show_stats(self):
        """Afficher les statistiques globales"""
        print(f"\n{'='*60}")
        print("📈 STATISTIQUES GLOBALES")
        print(f"{'='*60}")
        
        # Sessions
        self.cursor.execute("SELECT COUNT(*) FROM sessions")
        total_sessions = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM sessions WHERE status = 'COMPLETED'")
        completed_sessions = self.cursor.fetchone()[0]
        
        # Emails
        self.cursor.execute("SELECT COUNT(*) FROM email_logs")
        total_emails = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM email_logs WHERE status = 'SUCCESS'")
        success_emails = self.cursor.fetchone()[0]
        
        # Templates, sujets, from lines
        self.cursor.execute("SELECT COUNT(*) FROM templates WHERE is_active = 1")
        active_templates = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM subjects WHERE is_active = 1")
        active_subjects = self.cursor.fetchone()[0]
        
        self.cursor.execute("SELECT COUNT(*) FROM from_lines WHERE is_active = 1")
        active_froms = self.cursor.fetchone()[0]
        
        # Afficher
        print(f"Sessions totales: {total_sessions}")
        print(f"Sessions complétées: {completed_sessions}")
        print(f"Emails envoyés: {success_emails}/{total_emails} ({(success_emails/total_emails*100 if total_emails>0 else 0):.1f}%)")
        print(f"Templates actifs: {active_templates}")
        print(f"Sujets actifs: {active_subjects}")
        print(f"From lines actives: {active_froms}")
        print(f"{'='*60}")
        
        # Dernières sessions
        print("\n📋 5 DERNIÈRES SESSIONS:")
        print(f"{'-'*60}")
        self.cursor.execute('''
            SELECT session_id, start_time, sent_emails, failed_emails, status
            FROM sessions ORDER BY start_time DESC LIMIT 5
        ''')
        
        for row in self.cursor.fetchall():
            print(f"{row[0]}: {row[1]} | ✅{row[2]} ❌{row[3]} | {row[4]}")

def create_default_config():
    """Créer la configuration par défaut"""
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)
    
    # Configuration principale
    config = {
        "pause_after": 100,
        "pause_duration": 300,
        "test_interval": 50,
        "delay_between_emails": 1,
        "max_emails_per_session": 1000,
        "rotation_mode": "random",
        "enable_test_emails": True,
        "test_email_recipients": ["admin@example.com"],
        "postfix_config": {
            "myhostname": "localhost",
            "inet_interfaces": "loopback-only"
        }
    }
    
    with open(config_dir / "config.json", 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2)
    
    # Créer un exemple de liste d'emails
    email_list_dir = config_dir / "email_lists"
    email_list_dir.mkdir(exist_ok=True)
    
    with open(email_list_dir / "exemple.txt", 'w', encoding='utf-8') as f:
        f.write("test1@example.com\ntest2@example.com\ntest3@example.com\n")
    
    print("✅ Configuration par défaut créée dans le dossier 'config'")

def main():
    parser = argparse.ArgumentParser(
        description="Script d'envoi d'emails intelligent pour Google Cloud Shell"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commandes disponibles')
    
    # Commande: send
    send_parser = subparsers.add_parser('send', help='Envoyer des emails')
    send_parser.add_argument('--list-id', type=int, help='ID de la liste d\'emails')
    send_parser.add_argument('--list-name', type=str, help='Nom de la liste d\'emails')
    send_parser.add_argument('--max', type=int, help='Nombre maximum d\'emails')
    send_parser.add_argument('--no-resume', action='store_true', help='Ne pas reprendre depuis la dernière position')
    send_parser.add_argument('--pause-after', type=int, help='Pause après X emails')
    send_parser.add_argument('--pause-duration', type=int, help='Durée de la pause en secondes')
    
    # Commande: add
    add_parser = subparsers.add_parser('add', help='Ajouter des éléments')
    add_parser.add_argument('--template', type=str, help='Ajouter un template (spécifier --file)')
    add_parser.add_argument('--subject', type=str, help='Ajouter un sujet')
    add_parser.add_argument('--from-line', nargs=2, metavar=('NAME', 'EMAIL'), help='Ajouter une from line')
    add_parser.add_argument('--email-list', nargs=2, metavar=('NAME', 'FILE'), help='Ajouter une liste d\'emails')
    add_parser.add_argument('--file', type=str, help='Fichier pour le template')
    add_parser.add_argument('--weight', type=int, default=1, help='Poids pour la rotation')
    
    # Commande: stats
    stats_parser = subparsers.add_parser('stats', help='Afficher les statistiques')
    
    # Commande: config
    config_parser = subparsers.add_parser('config', help='Gérer la configuration')
    config_parser.add_argument('--create-default', action='store_true', help='Créer la configuration par défaut')
    config_parser.add_argument('--show', action='store_true', help='Afficher la configuration')
    
    # Commande: test
    test_parser = subparsers.add_parser('test', help='Tester le système')
    test_parser.add_argument('--email', type=str, help='Email pour le test')
    
    args = parser.parse_args()
    
    print("="*60)
    print("🤖 SCRIPT D'ENVOI D'EMAILS INTELLIGENT")
    print("="*60)
    
    if args.command == 'config' and args.create_default:
        create_default_config()
        return
    
    # Initialiser le gestionnaire
    manager = EmailManager("config")
    
    if args.command == 'send':
        # Appliquer les paramètres de pause si spécifiés
        if args.pause_after:
            manager.pause_after = args.pause_after
        if args.pause_duration:
            manager.pause_duration = args.pause_duration
            
        manager.send_bulk_emails(
            list_id=args.list_id,
            max_emails=args.max,
            resume=not args.no_resume
        )
        
    elif args.command == 'add':
        if args.template and args.file:
            if Path(args.file).exists():
                with open(args.file, 'r', encoding='utf-8') as f:
                    content = f.read()
                manager.add_template(args.template, content, args.weight)
            else:
                print(f"❌ Fichier non trouvé: {args.file}")
                
        elif args.subject:
            manager.add_subject(args.subject, args.weight)
            
        elif args.from_line:
            manager.add_from_line(args.from_line[0], args.from_line[1], args.weight)
            
        elif args.email_list:
            manager.add_email_list(args.email_list[0], args.email_list[1])
            
        else:
            print("❌ Spécifiez ce que vous voulez ajouter")
            
    elif args.command == 'stats':
        manager.show_stats()
        
    elif args.command == 'test':
        # Tester avec un email spécifique
        test_email = args.email or "test@localhost"
        template, subject, from_line = manager.get_next_combination()
        
        print(f"🧪 Test d'envoi à: {test_email}")
        print(f"   Template: {template['name']}")
        print(f"   Sujet: {subject['text']}")
        print(f"   De: {from_line['name']} <{from_line['email']}>")
        
        if manager.send_email(test_email, template, subject, from_line, "test_session"):
            print("✅ Test réussi!")
        else:
            print("❌ Test échoué")
            
    elif args.command == 'config' and args.show:
        print("📋 CONFIGURATION ACTUELLE:")
        print(json.dumps(manager.config, indent=2))
        
    else:
        print("\n🎯 UTILISATION:")
        print("  python3 send.py send [--list-id ID] [--max N] [--no-resume]")
        print("  python3 send.py add --template nom --file fichier.html")
        print("  python3 send.py add --subject \"Mon sujet\"")
        print("  python3 send.py add --from-line \"Nom\" email@exemple.com")
        print("  python3 send.py add --email-list \"Ma liste\" emails.txt")
        print("  python3 send.py stats")
        print("  python3 send.py test [--email test@exemple.com]")
        print("  python3 send.py config --create-default")
        print("\n📝 EXEMPLE COMPLET:")
        print("  1. python3 send.py config --create-default")
        print("  2. Éditez config/config.json et ajoutez vos emails dans config/email_lists/")
        print("  3. python3 send.py add --email-list \"Clients\" config/email_lists/clients.txt")
        print("  4. python3 send.py send --list-name \"Clients\" --pause-after 50")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Script terminé par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur: {str(e)}")
        import traceback
        traceback.print_exc()
