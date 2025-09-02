# 🤖 Discord Bot Multi-Fonctions

Un bot Discord polyvalent pour votre serveur 🛠️  
Inclut des fonctionnalités de **modération, sondages, statistiques, messages automatiques** et plus !

---

## ✨ Fonctionnalités
- 🎉 Messages de bienvenue et départ automatisés  
- 🗓️ Message quotidien programmé (avec APScheduler)  
- 📊 Sondages à choix multiple  
- 🔐 Générateur de mot de passe aléatoire  
- 🛡️ Modération : ban, kick, avertissements  
- 📈 Statistiques du serveur simplifiées  
- 🚫 Filtrage de mots interdits avec système d’avertissement progressif  

---

## 📦 Installation

Clonez ce dépôt :  

git clone https://github.com/kingoftech-v01/discord-bot.git

cd discord-bot

Installez les dépendances :  

pip install -r requirements.txt

---

## 🔑 Configuration

Créez un fichier `.env` à la racine du projet contenant vos informations sensibles (ne jamais le publier) :  

DISCORD_TOKEN=VOTRE_DISCORD_BOT_TOKEN

APPLICATION_ID=VOTRE_APPLICATION_ID

PUBLIC_KEY=VOTRE_PUBLIC_KEY

PRIVATE_KEY=VOTRE_PRIVATE_KEY

CHANNEL_ID=ID_DU_CHANNEL_DISCORD

Remplacez chaque valeur par les vôtres :  
- **DISCORD_TOKEN** : Token de votre bot sur le [Discord Developer Portal](https://discord.com/developers/applications)  
- **APPLICATION_ID** : ID de votre application Discord  
- **PUBLIC_KEY** et **PRIVATE_KEY** : Clés de votre application  
- **CHANNEL_ID** : ID numérique du channel où le bot doit envoyer les messages  

---

## 🚀 Lancement du bot

Démarrez le bot avec :  

python main.py


---

## ⚠️ Sécurité

- Gardez votre fichier `.env` **privé et sécurisé**.  
- Ajoutez `.env` dans votre `.gitignore` pour ne pas le pousser sur GitHub.  
- Ne partagez jamais publiquement vos tokens Discord.

---

## 📄 Licence

Projet sans licence spécifiée (usage privé ou personnel).  
Pour autoriser la collaboration ou redistribution, ajoutez une licence adaptée.

---

👤 Développé avec ❤️ par [kingoftech-v01](https://github.com/kingoftech-v01)

