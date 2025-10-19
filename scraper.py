import os
import re
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from icalendar import Calendar, Event
from bs4 import BeautifulSoup
import pytz

# ============================================
# CONFIGURATION
# ============================================

# Charger les variables d'environnement depuis .env (pour test local uniquement)
if os.path.exists('.env'):
    with open('.env') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                key, value = line.strip().split('=', 1)
                os.environ[key] = value

# Variables d'environnement requises
USERNAME = os.environ.get('EDC_USERNAME')
PASSWORD = os.environ.get('EDC_PASSWORD')
HASH_URL = os.environ.get('EDC_HASH_URL')
USER_ID = os.environ.get('EDC_USER_ID')

# Vérification de la configuration
if not all([USERNAME, PASSWORD, HASH_URL, USER_ID]):
    print("❌ Variables d'environnement manquantes!")
    print("Configurez : EDC_USERNAME, EDC_PASSWORD, EDC_HASH_URL, EDC_USER_ID")
    exit(1)

SERVER_ID = "C"
WEEKS_TO_FETCH = 52

# ============================================
# FONCTIONS UTILITAIRES
# ============================================


def get_wednesdays(num_weeks=52):
    """Génère les mercredis jusqu'à fin septembre 2026"""
    today = datetime.now()
    days_since_wednesday = (today.weekday() - 2) % 7
    current_week_wednesday = today - timedelta(days=days_since_wednesday)
    end_date = datetime(2026, 9, 30)
    weeks_diff = (end_date - current_week_wednesday).days // 7

    wednesdays = []
    for i in range(weeks_diff + 1):
        week_wednesday = current_week_wednesday + timedelta(weeks=i)
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
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    all_events = []

    try:
        print("🔐 Connexion à 360learning...")
        page.goto('https://reseau-cd.360learning.com/', timeout=30000)
        page.wait_for_load_state('networkidle')

        # Cliquer sur "Se connecter"
        try:
            page.click('text=Se connecter', timeout=5000)
            page.wait_for_load_state('networkidle')
        except:
            pass

        page.wait_for_load_state('networkidle')

        # Attendre le chargement du formulaire
        import time
        time.sleep(2)

        # Remplir le champ username/email
        username_selectors = [
            'input[type="email"]',
            'input[name="username"]',
            'input[name="email"]',
            'input[id="username"]',
            'input[id="email"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="identifiant" i]',
            'input.form-control',
        ]

        username_filled = False
        for selector in username_selectors:
            try:
                if page.locator(selector).count() > 0:
                    page.fill(selector, USERNAME)
                    username_filled = True
                    break
            except:
                continue

        if not username_filled:
            raise Exception("Champ username introuvable")

        # Remplir le champ mot de passe
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
                    password_filled = True
                    break
            except:
                continue

        if not password_filled:
            raise Exception("Champ password introuvable")

        # Soumettre le formulaire
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
                submitted = True
                break
            except:
                continue

        if not submitted:
            page.keyboard.press('Enter')

        # Récupérer l'emploi du temps pour chaque semaine
        wednesdays = get_wednesdays(WEEKS_TO_FETCH)

        for idx, date in enumerate(wednesdays, 1):
            print(
                f"📅 Récupération semaine {idx}/{len(wednesdays)} ({date})...")

            url = build_edt_url(date)
            page.goto(url, timeout=30000)
            page.wait_for_load_state('networkidle')

            # Attendre que le contenu soit chargé
            try:
                page.wait_for_selector('table, .event, .course', timeout=10000)
            except:
                print(f"⚠️  Pas de contenu pour la semaine du {date}")
                continue

            html_content = page.content()
            events = parse_schedule(html_content, date)
            all_events.extend(events)
            print(f"   → {len(events)} événements trouvés")

    except Exception as e:
        print(f"❌ Erreur lors de la connexion ou du scraping: {e}")
        page.screenshot(path='error_screenshot.png')

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
    jours = soup.find_all('div', class_='Jour')
    jour_mapping = {}
    paris_tz = pytz.timezone('Europe/Paris')

    # Parser les jours pour créer un mapping position -> date
    for jour in jours:
        style = jour.get('style', '')
        left_match = re.search(r'left:\s*([\d.]+)%', style)

        if left_match:
            left_pos = float(left_match.group(1))
            td_jour = jour.find('td', class_='TCJour')

            if td_jour:
                date_text = td_jour.get_text(strip=True)

                try:
                    match = re.search(r'(\w+)\s+(\d+)\s+(\w+)', date_text)
                    if match:
                        jour_nom, jour_num, mois_nom = match.groups()

                        mois_fr = {
                            'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
                            'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
                            'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
                        }

                        mois_num = mois_fr.get(mois_nom.lower())

                        if mois_num:
                            base_date = datetime.strptime(
                                week_date, '%m/%d/%Y')
                            annee = base_date.year
                            date_obj = datetime(annee, mois_num, int(jour_num))
                            jour_mapping[left_pos] = (date_text, date_obj)
                except Exception as e:
                    pass

    # Récupérer tous les cours
    cours = soup.find_all('div', class_='Case')

    for case in cours:
        try:
            event = extract_event_info(case, jour_mapping, paris_tz)
            if event:
                events.append(event)
        except Exception as e:
            pass

    return events


def extract_event_info(case_div, jour_mapping, paris_tz):
    """Extrait les informations d'un cours depuis une div.Case"""
    style = case_div.get('style', '')
    left_match = re.search(r'left:\s*([\d.]+)%', style)

    if not left_match:
        return None

    left_pos = float(left_match.group(1))

    # Trouver le jour correspondant
    jour_date = None
    min_diff = float('inf')

    for jour_left, (date_text, date_obj) in jour_mapping.items():
        diff = abs(jour_left - left_pos)
        if diff < min_diff:
            min_diff = diff
            jour_date = date_obj

    if not jour_date:
        return None

    # Récupérer le contenu de la table
    table = case_div.find('table', class_='TCase')
    if not table:
        return None

    rows = table.find_all('tr')

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

    lines = []
    classe_keywords = ['tronc', 'b3', 'asrbd', 'classe',
                       'groupe', '25/26', '26/27', 'epsi', 'ds', 'cc all']

    for keyword in classe_keywords:
        if keyword in prof_text.lower():
            idx = prof_text.lower().find(keyword)
            if idx > 0:
                formateur_part = prof_text[:idx].strip()
                classe_part = prof_text[idx:].strip()

                if formateur_part:
                    lines = [formateur_part, classe_part]
                else:
                    lines = [classe_part]
                break

    if not lines:
        lines = [prof_text] if prof_text else []

    formateur = lines[0] if len(lines) > 0 else ""
    classe = lines[1] if len(lines) > 1 else ""

    # Ligne 3 : Horaires et salle
    horaire_row = rows[2]
    horaire_td = horaire_row.find('td', class_='TChdeb')
    salle_td = horaire_row.find('td', class_='TCSalle')

    if not horaire_td:
        return None

    horaire_text = horaire_td.get_text(strip=True)
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

    with sync_playwright() as playwright:
        events = login_and_get_schedule(playwright)

    if not events:
        print("\n⚠️  Aucun événement trouvé.")
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


if __name__ == '__main__':
    main()
