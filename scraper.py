import os
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event
from bs4 import BeautifulSoup
import pytz

# ============================================
# CONFIGURATION - À PERSONNALISER
# ============================================

# Charger les variables d'environnement depuis .env (pour test local uniquement)
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# ✅ SÉCURISÉ - Les valeurs viennent uniquement des variables d'environnement
USERNAME = os.environ.get('EDC_USERNAME')
PASSWORD = os.environ.get('EDC_PASSWORD')
HASH_URL = os.environ.get('EDC_HASH_URL')
USER_ID = os.environ.get('EDC_USER_ID')

# Vérification que tout est configuré
if not all([USERNAME, PASSWORD, HASH_URL, USER_ID]):
    print("❌ Variables d'environnement manquantes!")
    print("Configurez : EDC_USERNAME, EDC_PASSWORD, EDC_HASH_URL, EDC_USER_ID")
    exit(1)

SERVER_ID = "C"
WEEKS_TO_FETCH = 8  # Nombre de semaines à récupérer

# ============================================
# FONCTIONS UTILITAIRES
# ============================================


def get_wednesdays(num_weeks=8):
    """Génère la liste des mercredis pour les N prochaines semaines"""
    today = datetime.now()
    # Trouve le prochain mercredi (ou aujourd'hui si c'est mercredi)
    days_until_wednesday = (2 - today.weekday()) % 7
    next_wednesday = today + timedelta(days=days_until_wednesday)

    wednesdays = []
    for i in range(num_weeks):
        week_wednesday = next_wednesday + timedelta(weeks=i)
        wednesdays.append(week_wednesday.strftime('%m/%d/%Y'))

    return wednesdays


def build_edt_url(date):
    """Construit l'URL de l'emploi du temps pour une date donnée"""
    return (f"https://ws-edt-cd.wigorservices.net/WebPsDyn.aspx?"
            f"action=posEDTLMS&serverID={SERVER_ID}&Tel={USER_ID}"
            f"&date={date}&hashURL={HASH_URL}")

# ============================================
# AUTHENTIFICATION ET SCRAPING
# ============================================


def login_and_get_schedule(playwright):
    """Se connecte et récupère l'emploi du temps"""

    browser = playwright.chromium.launch(
        headless=False,  # Voir le navigateur
        slow_mo=1000     # Ralentir les actions
    )
    context = browser.new_context()
    page = context.new_page()

    all_events = []

    try:
        print("🔐 Connexion à 360learning...")

        # Étape 1 : Accéder à 360learning
        page.goto('https://reseau-cd.360learning.com/', timeout=30000)
        page.wait_for_load_state('networkidle')

        # Étape 2 : Chercher et cliquer sur "Se connecter"
        print("\n🔍 Recherche du bouton de connexion...")

        try:
            # Essayer de cliquer sur "Se connecter (étudiants & intervenants)"
            page.click('text=Se connecter', timeout=5000)
            print("   ✅ Cliqué sur 'Se connecter'")
            page.wait_for_load_state('networkidle')
        except:
            print("   ⚠️  Bouton 'Se connecter' non trouvé, on continue...")

        # Attendre que le formulaire de connexion apparaisse
        page.wait_for_load_state('networkidle')

        # Étape 3 : Remplir le formulaire
        print("\n📝 Remplissage du formulaire...")

        # Attendre un peu que la page charge complètement
        import time
        time.sleep(2)

        # Essayer différents sélecteurs pour le champ username/email
        username_selectors = [
            'input[type="email"]',
            'input[name="username"]',
            'input[name="email"]',
            'input[id="username"]',
            'input[id="email"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="identifiant" i]',
            'input.form-control',  # Classe commune
        ]

        username_filled = False
        for selector in username_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.fill(selector, USERNAME)
                    print(f"   ✅ Email/Username rempli avec: {selector}")
                    username_filled = True
                    break
            except Exception as e:
                continue

        if not username_filled:
            # Prendre une capture d'écran pour debug
            page.screenshot(path='debug_login_form.png')
            print("   ❌ Impossible de trouver le champ email/username")
            print("   📸 Voir debug_login_form.png")
            raise Exception("Champ username introuvable")

        # Champ mot de passe
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id="password"]',
        ]

        password_filled = False
        for selector in password_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.fill(selector, PASSWORD)
                    print(f"   ✅ Mot de passe rempli avec: {selector}")
                    password_filled = True
                    break
            except Exception as e:
                continue

        if not password_filled:
            page.screenshot(path='debug_login_form.png')
            print("   ❌ Impossible de trouver le champ password")
            raise Exception("Champ password introuvable")

        # Étape 4 : Soumettre le formulaire
        print("\n🔐 Soumission du formulaire...")

        # Essayer de trouver et cliquer sur le bouton de soumission
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Connexion")',
            'button:has-text("Se connecter")',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button.btn-primary',
            'button.submit',
        ]

        submitted = False
        for selector in submit_selectors:
            try:
                page.click(selector, timeout=3000)
                print(f"   ✅ Bouton soumis avec: {selector}")
                submitted = True
                break
            except:
                continue

        if not submitted:
            print("   ⚠️  Tentative avec Enter...")
            page.keyboard.press('Enter')

        # Étape 5 : Récupérer l'emploi du temps pour chaque semaine
        wednesdays = get_wednesdays(WEEKS_TO_FETCH)

        for idx, date in enumerate(wednesdays, 1):
            print(
                f"📅 Récupération semaine {idx}/{len(wednesdays)} ({date})...")

            url = build_edt_url(date)
            page.goto(url, timeout=30000)

            # Dans la boucle de récupération, après page.goto(url)
            if "10/22" in date:
                with open('debug_semaine_22oct.html', 'w', encoding='utf-8') as f:
                    f.write(html_content)
                print("   📄 HTML de la semaine du 22 sauvegardé pour debug")

            page.wait_for_load_state('networkidle')

            # Attendre que le contenu soit chargé
            try:
                page.wait_for_selector('table, .event, .course', timeout=10000)
            except:
                print(f"⚠️  Pas de contenu pour la semaine du {date}")
                continue

            # Récupérer le HTML
            html_content = page.content()
            events = parse_schedule(html_content, date)
            all_events.extend(events)

            print(f"   → {len(events)} événements trouvés")

    except Exception as e:
        print(f"❌ Erreur lors de la connexion ou du scraping: {e}")
        # Prendre une capture d'écran pour debug
        page.screenshot(path="error_screenshot.png")
        print("📸 Capture d'écran sauvegardée dans error_screenshot.png")

    finally:
        browser.close()

    return all_events

# ============================================
# PARSING HTML
# ============================================


def parse_schedule(html_content, week_date):
    """Parse le HTML de l'emploi du temps et extrait les événements"""
    soup = BeautifulSoup(html_content, 'html.parser')
    events = []

    # Récupérer tous les jours de la semaine
    jours = soup.find_all('div', class_='Jour')
    jour_mapping = {}  # {position_left: (date_str, date_obj)}

    paris_tz = pytz.timezone('Europe/Paris')

    # Parser les jours pour créer un mapping position -> date
    for jour in jours:
        style = jour.get('style', '')
        left_match = re.search(r'left:\s*([\d.]+)%', style)

        if left_match:
            left_pos = float(left_match.group(1))

            # Extraire la date du jour
            td_jour = jour.find('td', class_='TCJour')
            if td_jour:
                # Ex: "Mardi 30 Septembre"
                date_text = td_jour.get_text(strip=True)

                # Parser la date
                try:
                    # Extraire jour et mois
                    match = re.search(r'(\w+)\s+(\d+)\s+(\w+)', date_text)
                    if match:
                        jour_nom, jour_num, mois_nom = match.groups()

                        # Convertir le mois français en numéro
                        mois_fr = {
                            'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
                            'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
                            'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
                        }

                        mois_num = mois_fr.get(mois_nom.lower())

                        if mois_num:
                            # Déterminer l'année (basée sur week_date)
                            base_date = datetime.strptime(
                                week_date, '%m/%d/%Y')
                            annee = base_date.year

                            # Créer la date
                            date_obj = datetime(annee, mois_num, int(jour_num))
                            jour_mapping[left_pos] = (date_text, date_obj)
                except Exception as e:
                    print(f"⚠️  Erreur parsing date '{date_text}': {e}")

    # Récupérer tous les cours (divs avec class="Case")
    cours = soup.find_all('div', class_='Case')

    print(
        f"   📊 {len(cours)} cours trouvés, {len(jour_mapping)} jours identifiés")

    # DEBUG - Liste tous les cours détectés
    for idx, case in enumerate(cours, 1):
        titre_elem = case.find('td', class_='TCase')
        if titre_elem:
            titre = titre_elem.get_text(strip=True)
            print(f"      Cours {idx}: {titre[:30]}...")

    for idx, case in enumerate(cours, 1):
        try:
            event = extract_event_info(case, jour_mapping, paris_tz)
            if event:
                events.append(event)
        except Exception as e:
            print(f"⚠️  Erreur cours {idx}: {e}")

    return events


def extract_event_info(case_div, jour_mapping, paris_tz):
    """Extrait les informations d'un cours depuis une div.Case"""

    # DEBUG - Afficher TOUS les cours traités
    titre_elem = case_div.find('td', class_='TCase')
    if titre_elem:
        titre_debug = titre_elem.get_text(strip=True)
        if "Election" in titre_debug or "Info" in titre_debug or "certification" in titre_debug:
            print(f"\n      🔍 DÉBUT traitement: {titre_debug}")

    # Récupérer la position left pour déterminer le jour
    style = case_div.get('style', '')

    # DEBUG - Afficher le style complet pour ces cours
    if titre_elem and ("Election" in titre_debug or "Info" in titre_debug or "certification" in titre_debug):
        # Premiers 200 caractères
        print(f"      📋 Style complet: {style[:200]}")

    left_match = re.search(r'left:([\d.]+)%', style)

    left_match = re.search(r'left:\s*([\d.]+)%', style)

    # DEBUG - Tester le regex
    if titre_elem and ("Election" in titre_debug or "Info" in titre_debug or "certification" in titre_debug):
        regex1 = re.search(r'left:\s*([\d.]+)%', style)
        regex2 = re.search(r'left:\s*(\d+\.\d+)%', style)
        regex3 = re.search(r'left: ([\d.]+)%', style)

        print(f"      🧪 Test regex 1: {regex1}")
        print(f"      🧪 Test regex 2: {regex2}")
        print(f"      🧪 Test regex 3: {regex3}")

        # Test manuel
        if 'left: 103.12%' in style:
            print(f"      ✅ 'left: 103.12%' trouvé dans le style")

    # # Remplacez la ligne du regex par :
    # if 'left:' in style:
    #     parts = style.split('left:')[1].split(';')[0].strip()
    #     left_value = re.search(r'([\d.]+)%', parts)
    #     if left_value:
    #         left_pos = float(left_value.group(1))
    #     else:
    #         return None
    # else:
    #     return None

    if not left_match:
        if titre_elem and ("Election" in titre_debug or "Info" in titre_debug):
            print(f"      ❌ Pas de left_match pour: {titre_debug}")
        return None

    left_pos = float(left_match.group(1))

    if titre_elem and ("Election" in titre_debug or "Info" in titre_debug):
        print(f"      ✅ left_pos: {left_pos}")

    # Trouver le jour correspondant (le plus proche)
    jour_date = None
    min_diff = float('inf')

    for jour_left, (date_text, date_obj) in jour_mapping.items():
        diff = abs(jour_left - left_pos)
        if diff < min_diff:
            min_diff = diff
            jour_date = date_obj

    if not jour_date:
        if titre_elem and ("Election" in titre_debug or "Info" in titre_debug):
            print(f"      ❌ Pas de jour_date trouvé pour: {titre_debug}")
            print(f"         jour_mapping: {jour_mapping}")
        return None

    if titre_elem and ("Election" in titre_debug or "Info" in titre_debug):
        print(f"      ✅ jour_date: {jour_date}")

    # Récupérer le contenu de la table
    table = case_div.find('table', class_='TCase')
    if not table:
        if titre_elem and ("Election" in titre_debug or "Info" in titre_debug):
            print(f"      ❌ Pas de table TCase pour: {titre_debug}")
        return None

    rows = table.find_all('tr')

    # DEBUG - Vérifier le nombre de lignes
    titre_debug = table.find('td', class_='TCase')
    if titre_debug:
        titre_text = titre_debug.get_text(strip=True)
        if "Election" in titre_text or "Info" in titre_text or "certification" in titre_text:
            print(
                f"      🔍 DEBUG '{titre_text}': {len(rows)} lignes de tableau")
            for i, row in enumerate(rows, 1):
                print(f"         Ligne {i}: {row.get_text(strip=True)[:80]}")

    if len(rows) < 3:
        return None

    # Ligne 1 : Titre du cours
    titre_row = rows[0]
    titre_td = titre_row.find('td', class_='TCase')
    if not titre_td:
        return None

    titre = titre_td.get_text(strip=True)

    # Récupérer les liens Teams
    teams_links = []
    teams_div = titre_td.find('div', class_='Teams')
    if teams_div:
        for link in teams_div.find_all('a'):
            href = link.get('href', '')
            if href and 'StartMeetingTeams' in href:
                teams_links.append(href)

    # Ligne 2 : Formateur et classe
    prof_row = rows[1]
    prof_td = prof_row.find('td', class_='TCProf')
    if not prof_td:
        return None

    prof_text = prof_td.get_text(strip=True)

    # DEBUG - À ajouter temporairement
    if "Election" in titre or "Info" in titre:
        print(f"\n      🔍 DEBUG - Titre: {titre}")
        print(f"      📝 prof_text brut: '{prof_text}'")
        print(f"      📝 prof_text.split('\\n'): {prof_text.split(chr(10))}")

    # Séparer formateur et classe
    lines = [line.strip() for line in prof_text.split('\n') if line.strip()]

    # Détecter si c'est un cours sans formateur
    if len(lines) == 1:
        # Une seule ligne = probablement la classe, pas de formateur
        if any(keyword in lines[0].lower() for keyword in ['tronc', 'b3', 'classe', 'groupe', '25/26', '26/27']):
            formateur = None  # Pas de formateur
            classe = lines[0]
        else:
            # C'est probablement le formateur seul
            formateur = lines[0]
            classe = ""
    elif len(lines) >= 2:
        formateur = lines[0]
        classe = lines[1]
    else:
        formateur = None
        classe = ""

    # Construire la description
    description_parts = []

    # N'ajouter le formateur que s'il existe
    if formateur:
        description_parts.append(f"Formateur: {formateur}")

    if classe:
        description_parts.append(f"Classe: {classe}")

    if teams_links:
        description_parts.append(f"\nLiens Teams:")
        for i, link in enumerate(teams_links, 1):
            description_parts.append(f"  • Lien {i}: {link}")

    description = '\n'.join(description_parts)

    # Ligne 3 : Horaires et salle
    horaire_row = rows[2]
    horaire_td = horaire_row.find('td', class_='TChdeb')
    salle_td = horaire_row.find('td', class_='TCSalle')

    if not horaire_td:
        return None

    horaire_text = horaire_td.get_text(strip=True)  # Ex: "13:00 - 16:00"
    salle_text = salle_td.get_text(strip=True) if salle_td else ""

    # Parser les horaires
    time_match = re.search(
        r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})', horaire_text)

    if not time_match:
        return None

    heure_debut, minute_debut, heure_fin, minute_fin = time_match.groups()

    # Créer les datetime
    start_dt = paris_tz.localize(datetime(
        jour_date.year, jour_date.month, jour_date.day,
        int(heure_debut), int(minute_debut)
    ))

    end_dt = paris_tz.localize(datetime(
        jour_date.year, jour_date.month, jour_date.day,
        int(heure_fin), int(minute_fin)
    ))

    # Construire la description
    description_parts = []
    description_parts.append(f"Formateur: {formateur}")
    if classe:
        description_parts.append(f"Classe: {classe}")
    if teams_links:
        description_parts.append(f"\nLiens Teams:")
        for i, link in enumerate(teams_links, 1):
            description_parts.append(f"  • Lien {i}: {link}")

    description = '\n'.join(description_parts)

    return {
        'summary': titre,
        'start': start_dt,
        'end': end_dt,
        'location': salle_text,
        'description': description
    }

# ============================================
# GÉNÉRATION ICS
# ============================================


def create_ics_calendar(events):
    """Crée un fichier ICS à partir de la liste d'événements"""
    cal = Calendar()
    cal.add('prodid', '-//Emploi du Temps EDC//FR')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', 'Emploi du Temps')
    cal.add('x-wr-timezone', 'Europe/Paris')
    cal.add('x-wr-caldesc', 'Emploi du temps généré automatiquement')

    paris_tz = pytz.timezone('Europe/Paris')

    for event_data in events:
        if not event_data.get('start'):
            continue

        event = Event()
        event.add('summary', event_data.get('summary', 'Cours'))
        event.add('dtstart', event_data['start'])
        event.add('dtend', event_data['end'])
        event.add('dtstamp', datetime.now(paris_tz))

        if event_data.get('location'):
            event.add('location', event_data['location'])

        if event_data.get('description'):
            event.add('description', event_data['description'])

        # UID unique pour chaque événement
        uid = f"{event_data['start'].strftime('%Y%m%d%H%M%S')}-{hash(event_data['summary'])}@edc.local"
        event.add('uid', uid)

        cal.add_component(event)

    return cal

# ============================================
# MAIN
# ============================================


def main():
    """Fonction principale"""
    print("=" * 60)
    print("📚 RÉCUPÉRATION EMPLOI DU TEMPS → iCal")
    print("=" * 60)
    print()

    # Vérifier les credentials
    if USERNAME == 'votre.email@exemple.com':
        print("❌ Veuillez configurer vos identifiants dans le script!")
        print(
            "   Modifiez USERNAME et PASSWORD ou définissez les variables d'environnement:")
        print("   export EDC_USERNAME='votre.email@exemple.com'")
        print("   export EDC_PASSWORD='votre_mot_de_passe'")
        return

    # Lancer le scraping
    with sync_playwright() as playwright:
        events = login_and_get_schedule(playwright)

    if not events:
        print("\n⚠️  Aucun événement trouvé. Le parsing HTML doit être adapté.")
        print("   Consultez error_screenshot.png pour voir la structure de la page.")
        return

    print(f"\n✅ {len(events)} événements récupérés!")

    # Générer le fichier ICS
    print("\n📝 Génération du fichier ICS...")
    calendar = create_ics_calendar(events)

    output_file = 'emploi_du_temps.ics'
    with open(output_file, 'wb') as f:
        f.write(calendar.to_ical())

    print(f"✅ Fichier généré : {output_file}")
    print("\n📱 Pour l'importer dans Apple Calendar:")
    print("   1. Double-cliquez sur le fichier .ics")
    print("   2. Ou dans Calendar : Fichier > Importer")
    print("\n🔄 Pour une synchronisation automatique, consultez le README")


if __name__ == '__main__':
    main()
