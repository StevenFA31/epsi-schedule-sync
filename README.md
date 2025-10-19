# 🗓️ epsi-schedule-sync

**epsi-schedule-sync** est un projet cloud automatisé permettant de **récupérer automatiquement l’emploi du temps EPSI depuis Wigor (authentification CAS)**, puis de **générer un fichier calendrier (.ics)** mis à jour chaque jour via **GitHub Actions**.

> 💡 Projet réalisé dans le cadre d’un exercice scolaire EPSI : *communiquer avec une IA et concevoir un projet complet et fonctionnel sans modifier le code manuellement.*

---

## 📋 Table des matières
- [Aperçu](#-aperçu)
- [Fonctionnement](#-fonctionnement)
- [Installation locale](#-installation-locale)
- [Configuration](#-configuration)
- [Automatisation GitHub Actions](#-automatisation-github-actions)
- [Fichier généré](#-fichier-généré)
- [Dépendances](#-dépendances)
- [Exécution manuelle](#-exécution-manuelle)
- [Dépannage](#-dépannage)

---

## ✨ Aperçu

Ce script utilise **Playwright** pour automatiser la connexion CAS sur le portail **Wigor**, récupère les informations d’emploi du temps, les analyse avec **BeautifulSoup**, puis les convertit au format **ICS** grâce au module `icalendar`.

Le calendrier généré (`emploi_du_temps.ics`) est automatiquement **mis à jour chaque jour à 2h du matin** via un **workflow GitHub Actions**.

---

## ⚙️ Fonctionnement

1. Le workflow GitHub Actions s’exécute :
   - Tous les jours à **2h du matin**
   - Lors d’un **push sur la branche `main`**
   - Ou manuellement via **workflow_dispatch**

2. Il :
   - Configure un environnement Python 3.11
   - Installe les dépendances (`requirements.txt`)
   - Exécute le script `scraper.py`
   - Génère `emploi_du_temps.ics`
   - Commit et push automatiquement le fichier mis à jour sur le dépôt

---

## 🧩 Installation locale

Si tu veux exécuter le script manuellement sur ta machine :

```bash
# Cloner le dépôt
git clone https://github.com/<ton-utilisateur>/epsi-schedule-sync.git
cd epsi-schedule-sync

# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate   # ou venv\Scripts\activate sous Windows

# Installer les dépendances
pip install -r requirements.txt

# (Optionnel) Installer Chromium pour Playwright
playwright install chromium
````

---

## 🔐 Configuration

Avant d’exécuter le script, tu dois définir les variables d’environnement suivantes (ou les secrets GitHub correspondants) :

| Variable       | Description                                |
| -------------- | ------------------------------------------ |
| `EDC_USERNAME` | Identifiant EPSI (CAS)                     |
| `EDC_PASSWORD` | Mot de passe EPSI                          |
| `EDC_HASH_URL` | URL de base du portail Wigor (hash inclus) |
| `EDC_USER_ID`  | Identifiant utilisateur dans Wigor         |

Exemple en local :

```bash
export EDC_USERNAME="prenom.nom@epsi.fr"
export EDC_PASSWORD="tonmotdepasse"
export EDC_HASH_URL="https://<url-wigor>/Edt"
export EDC_USER_ID="12345"
```

---

## 🤖 Automatisation GitHub Actions

Le fichier [`update-calendar.yml`](.github/workflows/update-calendar.yml) gère l’automatisation complète.

### Exemple de workflow :

```yaml
on:
  schedule:
    - cron: '0 2 * * *'
  workflow_dispatch:
  push:
    branches: [ main ]
```

Ce workflow :

* S’exécute chaque jour à 2h
* Met à jour `emploi_du_temps.ics`
* Commit et push le fichier avec un message du type :

  ```
  Update calendar - Mon Oct 19 02:00:00 UTC 2025
  ```

---

## 📅 Fichier généré

* **Nom :** `emploi_du_temps.ics`
* **Format :** [iCalendar](https://icalendar.org/)
* **Usage :** Importable dans Google Calendar, Outlook, Apple Calendar, etc.

---

## 🧰 Dépendances

Les dépendances principales sont listées dans [`requirements.txt`](requirements.txt) :

```text
playwright==1.40.0
beautifulsoup4==4.12.2
icalendar==5.0.11
pytz==2023.3
lxml==4.9.3
```

---

## ▶️ Exécution manuelle

Pour exécuter le script directement :

```bash
python scraper.py
```

Le script générera automatiquement le fichier `emploi_du_temps.ics` dans le répertoire courant.

---

## 🧯 Dépannage

| Problème                  | Cause possible                       | Solution                                    |
| ------------------------- | ------------------------------------ | ------------------------------------------- |
| Erreur Playwright         | Chromium non installé                | `playwright install chromium`               |
| Erreur d’authentification | Identifiants EPSI incorrects         | Vérifie tes secrets GitHub                  |
| Pas de fichier ICS généré | Changement dans la structure du site | Vérifie le sélecteur HTML dans `scraper.py` |

---

## 👩‍💻 Auteurs

Projet réalisé par **Claude** et **ChatGPT** dans le cadre d’un exercice EPSI — *Créer un projet complet avec l’aide d’une IA.*

---

## 🪄 Remarques

* Le script est 100 % automatisé et **ne requiert aucune intervention manuelle** une fois configuré.
* Il peut facilement être adapté à d’autres établissements ou portails similaires utilisant Wigor/CAS.
