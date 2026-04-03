# Sémantický Indexer pro RAG
## Případová studie: AI-Assisted Engineering & Datová příprava

Tento repozitář obsahuje nástroj navržený jako lehká pre-processingová (dry-run) vrstva pro migraci nestrukturovaných dat z lokálních disků do vektorových databází a RAG (Retrieval-Augmented Generation) systémů.

Cílem nástroje není manipulace s daty, ale jejich stoprocentní ZMAPOVÁNÍ, SÉMANTICKÁ KLASIFIKACE, a NORMALIZACE (řešení encoding hell). Výstupem je strukturovaný manifest `rag_metadata.json`, který může přímo konzumovat RAG pipeline (např. LangChain).

## 1. MOTIVACE A ARCHITEKTONICKÝ ZÁMĚR
Tradiční skripty pro datový ingest do RAG systémů na lokálních Windows prostředích často naráží na následující blokátory, které tento skript řeší ještě PŘED předáním dat drahým LLM embedding modelům:

### A) Odolnost proti pádům na kódování (Encoding Hell)
Na běžném disku se mísí `utf-8`, staré české `cp1250` a systémové `latin-1`. Klasické `open(file)` skript neúprosně shodí (UnicodeDecodeError). Indexer proto aplikuje KASKÁDOVÉ DEKÓDOVÁNÍ (zkouší formáty, dokud neuspěje).

### B) Auto-konverze do UTF-8
Pokud nástroj detekuje staré české `cp1250` u textového souboru, automaticky jej otevře, převede a rovnou přeuloží do standardního `utf-8`. Toto je zásadní pro LLM modely od OpenAI či Googlu, které často halucinují, pokud jsou nuceny číst rozbitou diakritiku.

### C) Inteligentní datová filtrace (Text vs. Binárky)
Skript striktně dělí soubory:
- **TEXT (markdowny, kód, csv)**: Otevře, přečte obsah, vytáhne náhled.
- **BINÁRKY (zip, png, pdf, LiDAR .laz)**: Nečte obsah, pouze extrahuje metadata a cestu k souboru, aby nezahltil paměť "rozsypaným čajem".
- **BALAST (desktop.ini, .sqlite cache)**: Zcela ignoruje na I/O vrstvě.

## 2. AI-ASSISTED VÝVOJ: POST-MORTEM & LEKCE Z GEMINI
Tento skript je výsledkem přímé aplikace zkušeností z předchozího neúspěšného vývoje s LLM modelem Google Gemini. 

**[Proč předchozí iterace (s Gemini) selhaly](https://github.com/outpost2026/RAG-indexer/blob/main/development_notes.md)**
- **Ztráta kontextu ("Attention Sink")**: Po 5. iteraci model začal ignorovat systémová pravidla (boundaries).
- **Ztráta determinismu**: Model aplikoval "Mode Collapse" – odstraňoval nutné bezpečnostní sítě a začal kód svévolně rozšiřovat o nevyžádané a chybné funkce.
  
**Řešení v tomto projektu (Metodika Tvorby):**
Tento projekt byl od počátku vytvořen architekturou "Stavebních bloků". Byl oddělen nástroj (OpenCode/CLI) od LLM logiky. Kód je striktně modulární a dodržuje exaktní determinismus. LLM bylo použito výhradně jako analytický oponent pro cross-validaci a úpravu regexové taxonomie, nikoliv jako autonomní kodér bez dozoru.

## 3. EVOLUCE KÓDU (Kaskádový Vývoj napříč 3 verzemi)
Vývoj probíhal formou inkrementálních iterací (testováno na vzorku ~200 souborů):

* **Verze 1 (Baseline):** Oindexováno 86 souborů. Zjištěno značné procento neklasifikovaných souborů.
* **Verze 2 (Rozšíření taxonomie):** Rozšíření Regex pravidel (přidána LiDAR data, HTML reporty, atd.). Index stoupl na 94, ovšem skript začal číst i systémový odpad.
* **Verze 7 (Optimalizace a Filtrace):** Zavedení filtrů pro `desktop.ini` a SQLite cache. Zavedení auto-konverze kódování cp1250 na utf-8. Výsledkem je 92 naprosto čistých dokumentů připravených pro LLM.

## 4. POUŽITÍ (CLI)
**Spuštění skriptu:**
```bash
python universal_indexer_v7.py "C:\vaše_složka"
```

**Příklad výstupu v `02_rag_metadata.json`:**
```json
{
  "file_path": "GCP/gcp_miner_project/main.py",
  "document_type": "source_code_python",
  "encoding": "utf-8",
  "size_bytes": 4096,
  "last_modified": "2026-03-24T10:15:00",
  "content_snippet": "import os\nfrom google.cloud import storage..."
}
```

## 5. SHRNUTÍ
Tento skript demonstruje schopnost analyzovat byznysový a technický problém (vstupy z nečistého lokálního filesystému narušují RAG pipeline) a navrhnout deterministické, vysoce optimalizované řešení v jazyce Python s využitím moderních přístupů vývoje s asistencí AI (při současném pochopení a eliminaci jejích nevýhod).
