# Discord Bot Pro v2.0

Un bot Discord complet et professionnel avec des fonctionnalités avancées pour la gestion de communautés.

## Fonctionnalités

### Leveling & XP
- Gain d'XP automatique sur les messages
- Système de niveaux avec progression personnalisable
- Leaderboard et classements
- Rôles de récompense par niveau
- Commandes: `!rank`, `!leaderboard`, `!levelroles`

### Economie & Jeux
- Récompense quotidienne (`!daily`)
- Système de monnaie virtuelle
- Transferts entre utilisateurs
- Classement des plus riches
- **Trivia** avec questions de culture générale
- **Jeux**: dés, pile ou face, 8ball, pierre-feuille-ciseaux, machine à sous
- Commandes: `!balance`, `!give`, `!richest`, `!trivia`, `!roll`, `!coinflip`, `!8ball`, `!rps`, `!slot`

### Modération Avancée
- Auto-modération (spam, mots interdits, liens d'invitation)
- Ban, kick, mute/timeout avec logs
- Système d'avertissements persistant
- Seuil d'avertissements configurable
- Purge de messages, slowmode, lock/unlock de channels
- Commandes: `!ban`, `!kick`, `!mute`, `!unmute`, `!warn`, `!warnings`, `!purge`, `!slowmode`, `!lock`, `!unlock`

### Reaction Roles
- Attribution automatique de rôles via réactions
- Création de menus de rôles personnalisés
- Support des emojis personnalisés
- Commandes: `!reactionrole add`, `!reactionrole remove`, `!reactionrole create`, `!reactionrole list`

### Système de Tickets
- Panel de tickets avec boutons interactifs
- Création de tickets via modal
- Ajout/retrait de membres
- Transfert de tickets
- Fermeture avec transcript
- Commandes: `!ticket setup`, `!ticket close`, `!ticket add`, `!ticket remove`

### Messages de Bienvenue
- Messages de bienvenue personnalisables
- Messages de départ
- DM automatique aux nouveaux membres
- Variables dynamiques: `{user}`, `{server}`, `{member_count}`
- Commandes: `!setwelcome`, `!setwelcomemsg`, `!setgoodbyemsg`, `!testwelcome`

### Utilitaires
- Sondages simples et multiples
- Rappels/reminders
- Système AFK
- Memes aléatoires
- Informations serveur/utilisateur
- Calculatrice, ping, avatar
- Commandes: `!poll`, `!multipoll`, `!remind`, `!afk`, `!meme`, `!serverinfo`, `!userinfo`, `!avatar`, `!calc`, `!ping`

### Configuration
- Préfixe personnalisable par serveur
- Activation/désactivation des modules
- Channels de logs configurables
- Messages personnalisables
- Commandes: `!config`, `!help`, `!botinfo`, `!invite`

## Installation

### Prérequis
- Python 3.10+
- Un compte Discord Developer

### Étapes

1. **Cloner le dépôt**
```bash
git clone https://github.com/kingoftech-v01/discord-bot.git
cd discord-bot
```

2. **Créer un environnement virtuel (recommandé)**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

3. **Installer les dépendances**
```bash
pip install -r requirements.txt
```

4. **Configurer le bot**
```bash
cp .env.example .env
# Éditez .env avec vos tokens
```

5. **Lancer le bot**
```bash
python main.py
```

## Configuration

### Variables d'environnement (.env)

| Variable | Description | Défaut |
|----------|-------------|--------|
| `DISCORD_TOKEN` | Token du bot Discord | (requis) |
| `APPLICATION_ID` | ID de l'application Discord | (requis) |
| `BOT_PREFIX` | Préfixe des commandes | `!` |
| `XP_PER_MESSAGE` | XP gagné par message | `15` |
| `XP_COOLDOWN` | Cooldown XP en secondes | `60` |
| `DAILY_REWARD_MIN` | Récompense quotidienne min | `50` |
| `DAILY_REWARD_MAX` | Récompense quotidienne max | `200` |
| `WARN_THRESHOLD` | Seuil d'avertissements | `3` |

### Permissions Discord requises

Le bot nécessite les permissions suivantes:
- Gérer les rôles
- Gérer les channels
- Kick/Ban des membres
- Gérer les messages
- Envoyer des messages
- Ajouter des réactions
- Voir l'historique des messages

### Intents requis

Activez ces intents dans le Discord Developer Portal:
- Server Members Intent
- Message Content Intent

## Structure du projet

```
discord-bot/
├── main.py              # Point d'entrée principal
├── config.py            # Configuration centralisée
├── requirements.txt     # Dépendances Python
├── .env.example         # Template de configuration
├── .gitignore           # Fichiers à ignorer
├── cogs/                # Modules du bot
│   ├── admin.py         # Administration
│   ├── games.py         # Jeux et économie
│   ├── leveling.py      # Système de leveling
│   ├── moderation.py    # Modération
│   ├── reaction_roles.py# Reaction roles
│   ├── tickets.py       # Système de tickets
│   ├── utility.py       # Utilitaires
│   └── welcome.py       # Bienvenue/départ
├── utils/               # Utilitaires
│   └── database.py      # Gestion SQLite
└── data/                # Données (base de données)
```

## Commandes principales

| Commande | Description |
|----------|-------------|
| `!help` | Affiche toutes les commandes |
| `!config` | Voir/modifier la configuration |
| `!rank` | Voir son niveau et XP |
| `!leaderboard` | Classement XP |
| `!daily` | Récompense quotidienne |
| `!trivia` | Lancer une question trivia |
| `!ticket setup` | Installer le système de tickets |
| `!reactionrole create` | Créer un menu de rôles |

## Déploiement

### Render (Gratuit)
1. Créez un compte sur [Render](https://render.com)
2. Nouveau > Web Service
3. Connectez votre repo GitHub
4. Build: `pip install -r requirements.txt`
5. Start: `python main.py`
6. Ajoutez les variables d'environnement

### Railway (Simple)
1. Créez un compte sur [Railway](https://railway.app)
2. Nouveau projet > Deploy from GitHub
3. Ajoutez les variables d'environnement
4. Le bot se déploie automatiquement

### VPS (Recommandé pour la production)
```bash
# Avec systemd
sudo nano /etc/systemd/system/discord-bot.service

[Unit]
Description=Discord Bot
After=network.target

[Service]
User=your-user
WorkingDirectory=/path/to/discord-bot
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target

# Activer le service
sudo systemctl enable discord-bot
sudo systemctl start discord-bot
```

## Sécurité

- Ne partagez JAMAIS votre token Discord
- Gardez le fichier `.env` privé
- Utilisez des variables d'environnement en production
- Limitez les permissions du bot au strict nécessaire

## Support

Pour toute question ou problème:
- Ouvrez une issue sur GitHub
- Consultez la [documentation Discord.py](https://discordpy.readthedocs.io/)

## Licence

MIT License - Libre d'utilisation et de modification.

---

Développé avec Discord.py | [kingoftech-v01](https://github.com/kingoftech-v01)
