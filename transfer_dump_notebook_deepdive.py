import os
import requests
from bs4 import BeautifulSoup
import time
import random
import re
import sys
import logging
from pathlib import Path
from datetime import datetime
from google.cloud import storage

# ── KONFIGURACE GCP & TELEGRAM ────────────────────────────────────────────────
WORKSPACE_DIR = "/home/user/workspace/scraper"
Path(WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)

# Error Handling logování
logging.basicConfig(
    filename=f"{WORKSPACE_DIR}/error.log",
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "8725468950:AAH19oZ28SiZeaxILLdRLbMQLhJSpcnrA-I")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1341669174")
BUCKET_NAME      = os.environ.get("BUCKET_NAME", "gcp-miner-rag-data-01")

# Absolutní cesty pro Ephemeral VM (nahrazuje původní /tmp)
TMP_DIR     = WORKSPACE_DIR
INPUT_NAME  = "notebooky_rag_master.md"
OUTPUT_NAME = "notebooky_detail_index.md"
INPUT_FILE  = os.path.join(TMP_DIR, INPUT_NAME)
OUTPUT_FILE = os.path.join(TMP_DIR, OUTPUT_NAME)

DELAY_MIN = 2.0
DELAY_MAX = 4.5

# ── BOOLEAN SÉMANTICKÁ LOGIKA (DEEP GUARD v4.0) ───────────────────────────────
# ARCHITEKTURA FILTRŮ ZŮSTÁVÁ NEDOTČENA
BLACKLIST_EXACT = [
    "na opravu", "na díly", "odešel", "vadná deska", "vadný čip",
    "nenabíhá", "nejde zapnout", "vytopený", "politý", "prasklý",
    "bez ram", "bez paměti", "bez disku", "bez hdd", "bez ssd",
    "heslo v biosu", "zablokovaný", "pouze díly", "nenaběhne",
    "baterie ko", "baterka ko", "mrtvá baterie", "baterka mrtvá",
    "baterie mrtvá", "skoro mrtvá", "je skoro mrtvá",
    "baterie chybí", "chybí baterie", "bez baterie", "baterie není funkční",
    "baterie asi není funkční",
    "nedrží vůbec", "baterie nedrží",
    "vyndaná baterie", "baterie vyndaná",
    "baterie na výměnu", "špatná baterka",
    "baterie už nevydrží", "nevydrží baterie",
    "pracuje pouze s nabíječkou", "pracuje pouze s připojenou nabíječkou",
    "pouze na nabíječce", "pouze s nabíječkou", "pouze s adaptérem",
    "jen s nabíječkou", "funguje s nabíječkou", "jen na nabíječce",
    "funguje jen na nabíječce",
    "nefunkční bluetooth", "bluetooth nefunguje", "bt nefunguje",
    "bez bluetooth", "kromě baterie a bluetooth",
    "kromě bluetooth", "bluetooth nefunkcni",
    "baterie není součástí prodeje", "baterie není součástí",
    "není součástí prodeje",
    "baterie v ceně není", "bez baterky",
    "po své životnosti", "zcela po své životnosti",
    "na konci životnosti", "životnost baterie",
    "baterie dosloužila", "baterie dosluhuje",
    "baterie odepsána", "baterie odepsaná",
    "nutná výměna baterie", "potřebuje novou baterii",
    "potřebuje výměnu baterie",
    "nabíječka chybí", "nabijka chybí",
    "musí být zapojen", "musí být připojen k síti",
]

BLACKLIST_PATTERNS = [re.compile(p, re.IGNORECASE) for p in [
    r'❌\s*(baterie|bluetooth|baterka)',
    r'vydrž[íi]\s*(tak\s*|cca\s*|asi\s*)?\d{1,2}\s*min',
    r'výdrž\s*(\w+\s+)?(tak\s*|cca\s*)?\d{1,2}\s*min',
    r'drž[íi]\s*(tak\s*|cca\s*|jen\s*|asi\s*)?\d{1,2}\s*min',
    r'baterie\s+[01]:[0-5]\d\s*h',
    r'výdrž\s*[12]\s*hod',
    r'vydrž[íi]\s*[12]\s*hod',
    r'baterie\s*[-–]?\s*[12]\s*hod',
    r'baterie\s*[-–]?\s*[12]\s*h\b',
    r'vydrž[íi]\s*(tak\s*)?[12]\s*h\b',
    r'výdrž\s*(\w+\s+)?(cca\s*)?[12]\s*h\b',
    r'prodáv[aá][mn]\s+bez\s+nab[íi][žj]e[čc]ky',
    r'notebook\s+bez\s+nab[íi][žj]e[čc]ky',
    r'baterie\s+(je\s+)?(zcela\s+)?po\s+své\s+životnosti',
    r'baterie\s+(je\s+)?na\s+konci\s+(své\s+)?životnosti',
    r'baterie\s+není\s+součástí',
    r'nab[íi][žj]e[čc]ka\s+není\s+součástí',
    r'bez\s+funk[čc]ní\s+baterie',
]]

# ── GCS VRSTVA ────────────────────────────────────────────────────────────────
def sync_from_gcs():
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)

        blob_in = bucket.blob(INPUT_NAME)
        if blob_in.exists():
            blob_in.download_to_filename(INPUT_FILE)
            print(f"[i] Stažen {INPUT_NAME} z GCS.")
        else:
            raise FileNotFoundError(f"{INPUT_NAME} nenalezen v bucketu {BUCKET_NAME}.")

        blob_out = bucket.blob(OUTPUT_NAME)
        if blob_out.exists():
            blob_out.download_to_filename(OUTPUT_FILE)
            print(f"[i] Stažen existující {OUTPUT_NAME} z GCS (inkrementální režim).")
        else:
            Path(OUTPUT_FILE).write_text("--- Init Detail Index ---\n", encoding="utf-8")
            print(f"[i] {OUTPUT_NAME} na GCS nenalezen, vytvořen nový lokální.")
    except Exception as e:
        logging.error(f"GCS Sync-In Error: {e}")
        print(f"[!] Chyba při sync_from_gcs: {e}")
        raise

def sync_to_gcs():
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        bucket.blob(OUTPUT_NAME).upload_from_filename(OUTPUT_FILE)
        print(f"[i] Nahrán {OUTPUT_NAME} do GCS.")
    except Exception as e:
        logging.error(f"GCS Sync-Out Error: {e}")
        print(f"[!] Chyba při sync_to_gcs: {e}")

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram_doc(file_path, caption):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Telegram Error: Chybí konfigurace (Token/ID).")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    try:
        with open(file_path, 'rb') as f:
            r = requests.post(url, files={'document': f}, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption})
        if r.status_code == 200:
            print("[OK] Telegram report odeslán.")
        else:
            logging.error(f"Telegram API Error {r.status_code}: {r.text}")
            print(f"[!] Telegram API Error {r.status_code}: {r.text}")
    except Exception as e:
        logging.error(f"Kritická chyba Telegram: {e}")
        print(f"[!] Kritická chyba při odesílání na Telegram: {e}")

# ── FILTROVACÍ LOGIKA ─────────────────────────────────────────────────────────
def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().strip())

def is_blacklisted(full_text):
    normalized = normalize(full_text)
    for phrase in BLACKLIST_EXACT:
        if phrase in normalized:
            return True, f"EXACT: '{phrase}'"

    for pattern in BLACKLIST_PATTERNS:
        m = pattern.search(full_text)
        if m:
            return True, f"REGEX: '{pattern.pattern}' → '{m.group(0)}'"
    return False, None

# ── SCRAPING & PARSOVÁNÍ ──────────────────────────────────────────────────────
def parse_master_leads(filepath):
    content = Path(filepath).read_text(encoding="utf-8")
    # FIX: normalize CRLF → LF před parsováním, jinak \r zůstane v hodnotách
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    # FIX: původní regex r'---\n(.*?)\n---' selhal při blank řádcích uvnitř bloku
    # re.DOTALL + lookahead na '---' jako oddělovač
    blocks = re.findall(r'(?:^|\n)---\n(.*?)\n---(?:\n|$)', content, re.DOTALL)
    leads = []
    for block in blocks:
        data = {}
        for line in block.strip().split('\n'):
            if ':' in line:
                k, v = line.split(':', 1)
                data[k.strip()] = v.strip().strip('"')
        url = data.get('source_url') or data.get('url')
        if url:
            leads.append({
                'url':   url,
                'title': data.get('title', ''),
                'price': data.get('price', ''),
            })
    return leads

def get_already_processed(filepath):
    content = Path(filepath).read_text(encoding="utf-8")
    return set(re.findall(r'source_url:\s*"([^"]+)"', content))

def get_full_detail(url, session):
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "html.parser")
        desc_div = soup.find("div", class_="popis")
        if desc_div:
            for tag in desc_div.find_all(["span", "div"], class_="administrace"):
                tag.decompose()
            text = desc_div.get_text(separator="\n", strip=True)
            # FIX: whitespace-only text by prošel původním `if not full_text` checkem
            # ale neobsahoval žádnou reálnou informaci → přidán min. délkový guard
            if len(text.strip()) < 20:
                return ""
            return text
        return ""
    except Exception as e:
        return f"CHYBA EXTRAKCE: {e}"

# ── SÉMANTICKÁ EXTRAKCE & SCORING (NOVÉ) ─────────────────────────────────────
def extract_hw_hint(title, full_text):
    """
    OPRAVENO: RAM regex nyní vyžaduje kontextová slova pro zamezení falešným shodám u SSD.
    """
    combined = (title + " " + full_text).lower()
    hints = []
    
    if re.search(r'\bssd\b|nvme|m\.2', combined):
        hints.append("SSD")
    elif re.search(r'\bhdd\b', combined):
        hints.append("HDD")
        
    # Bezpečná detekce RAM s kontextovou kotvou
    ram = re.search(r'\b(4|8|16|32|64)\s*gb\s*(?:ram|paměť|ddr\d?|operační)\b|\b(?:ram|paměť|ddr\d?)\s*(?:je\s*)?(4|8|16|32|64)\s*gb\b', combined)
    if ram:
        velikost = ram.group(1) or ram.group(2)
        hints.append(f"{velikost}GB_RAM")
        
    if re.search(r'thinkpad|latitude|precision|elitebook|probook|macbook|xps', combined):
        hints.append("business_class")
        
    return "+".join(hints) if hints else "hw_nezmíněn"

def calculate_lead_score(title, full_text):
    """
    PŘIDÁNO: Autonomní skórování 1-100 pro RAG reranking.
    """
    score = 40 
    combined = (title + " " + full_text).lower()
    
    if re.search(r'\bssd\b|nvme|m\.2', combined):
        score += 15
        
    ram = re.search(r'\b(4|8|16|32|64)\s*gb\s*(?:ram|paměť|ddr\d?|operační)\b|\b(?:ram|paměť|ddr\d?)\s*(?:je\s*)?(4|8|16|32|64)\s*gb\b', combined)
    if ram:
        velikost = int(ram.group(1) or ram.group(2))
        if velikost >= 32: score += 25
        elif velikost >= 16: score += 15
        elif velikost >= 8: score += 5
        
    if re.search(r'thinkpad|latitude|precision|elitebook|probook|macbook|xps', combined):
        score += 15
        
    if re.search(r'baterie|výdrž|vydrž[íi]', combined):
        score += 5
        
    return min(score, 100)

# ── RAG VÝSTUP ────────────────────────────────────────────────────────────────
def write_rag_detail(f, lead, full_text, score):
    """OPRAVENO v4.3: Odstraněn misleading label PROVĚŘENÝ DETAIL.
    Přidán detail_chars (délka extrahovaného textu) jako integrity indikátor.
    Label nahrazen neutrálním DETAIL_RAW aby RAG nezaměňoval label za validaci.
    """
    url   = lead['url']
    title = lead['title'] or 'Bez názvu'
    price = lead['price'] or 'Neuvedena'

    battery_info = "Nezmíněna"
    if re.search(r'baterie|výdrž|vydrž[íi]|\d+\s*h\b|\d+\s*hod', full_text, re.IGNORECASE):
        battery_info = "V textu je info o baterii"

    hw_hint = extract_hw_hint(title, full_text)
    # Délka raw textu jako proxy pro kvalitu extrakce — krátký text = podezření na špatný DOM parse
    detail_chars = len(full_text.strip())
    truncated = len(full_text) > 1200

    f.write("---\n")
    f.write(f"title: \"{title}\"\n")
    f.write(f"source_url: \"{url}\"\n")
    f.write(f"price: \"{price}\"\n")
    f.write(f"lead_score: {score}\n")
    f.write(f"scraped_at: \"{datetime.now().isoformat()}\"\n")
    f.write(f"data_type: \"deep_detail\"\n")
    f.write(f"battery_hint: \"{battery_info}\"\n")
    f.write(f"hw_hint: \"{hw_hint}\"\n")
    f.write(f"detail_chars: {detail_chars}\n")
    f.write(f"detail_truncated: {truncated}\n")
    f.write("---\n\n")
    f.write(f"# {title}\n\n")
    f.write(f"**Cena:** {price} | **Skóre:** {score}/100 | **URL:** {url}\n\n")
    # Neutrální label bez implikace validace
    detail_text = full_text[:1200] + ("..." if truncated else "")
    f.write(f"**DETAIL_RAW:**\n\n{detail_text}\n\n***\n\n")

# ── ENTRY POINT ───────────────────────────────────────────────────────────────
def run_pipeline():
    try:
        print("[*] Startuje DeepDive selekce (v4.3)...")

        sync_from_gcs()

        all_leads      = parse_master_leads(INPUT_FILE)
        all_urls       = [l['url'] for l in all_leads]
        processed_urls = get_already_processed(OUTPUT_FILE)
        to_process     = [l for l in all_leads if l['url'] not in processed_urls]

        print(f"[i] Master: {len(all_urls)} celkem | Již zpracováno: {len(processed_urls)} | Fronta: {len(to_process)}")

        if not to_process:
            print("[INFO] Žádné nové inzeráty k analýze. Pipeline ukončen.")
            return

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})

        valid_count    = 0
        rejected_count = 0
        empty_count    = 0

        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            for i, lead in enumerate(to_process):
                url = lead['url']
                print(f"  [{i+1}/{len(to_process)}] Deep Scan: {url}")

                full_text = get_full_detail(url, session)

                if not full_text or full_text.startswith("CHYBA"):
                    print(f"      [?] PŘESKOČENO (prázdný nebo chybový popis)")
                    empty_count += 1
                    continue

                blacklisted, reason = is_blacklisted(full_text)
                if blacklisted:
                    print(f"      [X] ZAHOZENO → {reason}")
                    rejected_count += 1
                    continue
                
                # Výpočet skóre pro inzeráty, které prošly blacklistem
                score = calculate_lead_score(lead['title'], full_text)
                write_rag_detail(f, lead, full_text, score)
                
                valid_count += 1
                print(f"      [✓] OK | Skóre: {score}/100 | {lead['price']} | {lead['title'][:40]}")

                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        print(f"\n[✓] DeepDive dokončen.")
        print(f"    Propsáno:   {valid_count}/{len(to_process)}")
        print(f"    Zahozeno:   {rejected_count}/{len(to_process)}  (sémantická filtrace)")
        print(f"    Přeskočeno: {empty_count}/{len(to_process)}  (prázdný popis)")

        if valid_count > 0:
            sync_to_gcs()
            send_telegram_doc(OUTPUT_FILE, f"💎 DeepDive v4.3: {valid_count} nových leadů | integrity metadata přidána.")
            print("[OK] GCS sync + Telegram odeslán.")
        else:
            print("[INFO] Žádný vyhovující stroj. GCS sync přeskočen. Telegram mlčí.")
            
    except Exception as e:
        logging.error(f"Kritická chyba v pipeline: {str(e)}")
        print(f"[!] Došlo ke kritické chybě. Detaily v {WORKSPACE_DIR}/error.log")

run_deepdive = run_pipeline

if __name__ == "__main__":
    try:
        run_pipeline()
    finally:
        # Sebevražedný modul pro úsporu GCP kreditů
        print("[!] Úloha dokončena nebo selhala. Iniciuji autodestrukci VM...")
        os.system('sudo /sbin/shutdown -h now')