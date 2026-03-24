# Development Notes: Post Mortem vývoj RAG indexeru

## 1. Přehled projektu

### 1.1 Cíl projektu
Vytvoření **deterministického indexačního skriptu** pro klasifikaci a migraci souborů z lokálního repozitáře (`Repozitar_Dev`) do strukturovaného vaultu s YAML front-matter metadaty. Skript měl provádět:

- Klasifikaci souborů do 18+ kategorií (session_injekt, post_mortem, bms_telemetry, investment_arch, atd.)
- Content-aware analýzu (YAML front-matter, JSON struktura, textový obsah)
- Kaskádové dekódování (utf-8, cp1250, iso-8859-2)
- Generování JSON a TXT reportů pro audit

### 1.2 Technologický stack
| Komponenta | Volba |
|------------|-------|
| Vývojové prostředí | Geany 2.1 |
| Primární LLM | Gemini 3.1 Pro (placený tier) |
| Sekundární LLM | Claude Sonnet 4.6 (free tier) |
| Nástrojová vrstva | OpenCode CLI |
| Cílová platforma | Windows 11, Dell Latitude 5590 (8GB RAM) |

---

## 2. Chronologie vývoje

### 2.1 Fáze 1: Počáteční vývoj s Gemini (v3–v7)

**Období:** 1. týden sprintu

**Průběh:**
- Začátek s dobře strukturovaným kódem v3
- Gemini poskytovalo kvalitní výstupy, deterministické chování
- Klasifikační logika obsahovala 3 vrstvy (YAML → content → filename)
- Funkční JSON analýza pro strukturální typování

**Klíčový zlom:** Po 4–5 iteracích v rámci jedné session začala degradace.

### 2.2 Fáze 2: Degradace a halucinace Gemini (v7–v10)

**Příznaky degradace:**

| Iterace | Problém | Důsledek |
|---------|---------|----------|
| 5–7 | Filename heuristika přesunuta na první místo | `pitevni_kniha_v2_iot.md` klasifikováno jako `hardware_bom` |
| 8–9 | Odstranění YAML front-matter detekce | Ztracena schopnost respektovat existující metadata |
| 10 | Ztráta konzistence rozhraní | Funkce vracejí různé typy (tuple vs string) |
| 11–12 | Nevyžádané funkce | Skript změněn na migrační, vytvořen Vault export |
| 13+ | Scope chyby | Proměnné definované jen v některých větvích |

**Kritický moment:** Verze v10 byla označena operátorem jako "paskvil" – nefunkční, s chybami v základní logice.

### 2.3 Fáze 3: Přechod na Claude Sonnet 4.6

**Období:** 2. den sprintu

**Průběh:**
- Vložení torza kódu z v7 do nové session s Claude
- Během **jedné iterace** vytvořen funkční v8 s:
  - Obnovenou 3vrstvou klasifikací
  - Plnou taxonomií 18 typů
  - JSON fallbackem pro nevalidní soubory
  - Kódovou konzistencí

**Porovnání výkonu:**

| Metrika | Gemini (v10) | Claude (v8) |
|---------|--------------|-------------|
| Funkční kód | ❌ Ne | ✅ Ano |
| Klasifikační vrstvy | 1 | 3 |
| Podporované typy | 6 | 18 |
| JSON fallback | Částečný | Plný |
| YAML detekce | ❌ Chybí | ✅ Funkční |

---

## 3. Analýza selhání Gemini

### 3.1 Identifikované příčiny

#### 3.1.1 Architektonická omezení

| Problém | Mechanismus | Důsledek |
|---------|-------------|----------|
| **Attention sink** | Gemini preferuje poslední vstupy nad původními instrukcemi | System prompt (boundaries) ignorován po 5+ iteracích |
| **Lost in the middle** | Data uprostřed kontextu mají nižší váhu | Původní pravidla zapomenuta |
| **Mode collapse** | Návrat k nejjednodušším vzorům | Filename heuristika nahradila content analýzu |

#### 3.1.2 Post-tréninkové zaměření

| Aspekt | Gemini | Důsledek pro váš use case |
|--------|--------|---------------------------|
| **RLHF** | Optimalizace na "užitečnost" v širokém spektru | Přehnaná adaptace, ignorování striktních pravidel |
| **Kódové zaměření** | Sekundární | Specializace na kód nižší než u Claude |
| **Determinismus** | Nízká priorita | Teplota 0 negarantuje stejné výstupy |

#### 3.1.3 Degradační vzorec
Iterace 1-4: Kvalitní výstupy, respektování pravidel
↓
Iterace 5-7: Pořadí priorit narušeno (filename > content)
↓
Iterace 8-10: Odstraněny "redundantní" záchranné sítě
↓
Iterace 11+: Scope chyby, nevyžádané funkce, halucinace

---

## 4. Řešení operátora

### 4.1 Adopce OpenCode CLI

**Důvod:** Oddělení nástrojové vrstvy od modelové vrstvy

| Problém | Řešení OpenCode |
|---------|-----------------|
| Halucinace cest a souborů | Nástroje `read`, `write`, `edit` – model nemusí "hádat" |
| Ztráta kontextu | Session management udržuje strukturu |
| Nevyžádané funkce | Nástroje mají přesně definovaný kontrakt |

### 4.2 Adopce Geany 2.1

**Důvod:** Lehké, předvídatelné prostředí bez AI asistence

| Výhoda | Praktický přínos |
|--------|------------------|
| Žádná vestavěná AI | Eliminace rušivých "doporučení" |
| Rychlý start | < 2 sekundy vs 10+ sekund u VS Code |
| Syntax highlighting | Přehlednost kódu bez zbytečných funkcí |

### 4.3 Přechod na Claude Sonnet 4.6

**Rozhodnutí:** Po 3 neúspěšných iteracích s Gemini (v8–v10) přechod na Claude

**Výsledek:**
- 1 iterace = funkční v8
- 0 halucinací
- Plná taxonomie zachována
- 3vrstvá klasifikace obnovena

### 4.4 Stanovení provozních pravidel

| Pravidlo | Důvod |
|----------|-------|
| Max 3–4 iterace na session | Prevence degradace Gemini |
| Nová session pro každý logický blok | Reset kontextu |
| Verzování každé funkční verze | Možnost návratu k stabilnímu bodu |
| Claude pro finální migraci | Vyšší kvalita, konzistence |

---

## 5. Technické lekce

### 5.1 Determinismus v LLM asistenci

| Faktor | Vliv na determinismus |
|--------|----------------------|
| Teplota (temperature) | 0.1–0.2 = stabilní, 0.7+ = kreativní |
| System prompt | Udržuje pravidla napříč session |
| Nástrojová vrstva | Eliminuje halucinace cest a souborů |
| Session délka | >5 iterací = riziko degradace |

### 5.2 Klasifikační architektura – co funguje

**3vrstvá klasifikace (ověřená):**
VRSTVA 1: YAML front-matter (existující metadata)
↓
VRSTVA 2: Content-aware detekce (obsah je spolehlivější)
↓
VRSTVA 3: Filename fallback (záchranná síť)

**Klíčové poznatky:**
- Content > Filename – vždy
- YAML front-matter je nejvyšší priorita (respektuje manuální zásahy)
- JSON potřebuje strukturální analýzu, ne jen regex

---

## 6. Shrnutí

### 6.1 Hlavní zjištění

1. **Gemini není vhodný pro deterministické iterativní vývoj** – jeho adaptivita vede k degradaci po 5+ iteracích
2. **Boundaries a deterministické prompty nestačí** – problém je architektonický, ne prompt engineering
3. **Oddělení nástrojové a modelové vrstvy je klíčové** – OpenCode eliminuje halucinace
4. **Claude Sonnet 4.6 je pro kódování konzistentnější** – 1 iterace = funkční řešení vs 10+ iterací s Gemini

### 6.2 Úspěšný výsledek

- Funkční indexační skript v8 (Claude)
- 3vrstvá klasifikace obnovena
- JSON fallback implementován
- Plná taxonomie 18 typů
- OpenCode integrován do workflow

---

**Datum:** 2026-03-24  
**Autor:** Operátor / Claude Architekt  
**Verze dokumentu:** 1.0  
**Určeno:** Interní post mortem, tutoriál pro budoucí vývoj