#!/usr/bin/env python3
"""
Sémantický indexer pro RAG systémy - prochází lokální adresář, mapuje soubory,
klasifikuje je podle obsahu a názvu, a generuje strukturovaný JSON manifest.
"""

import os
import pathlib
import re
import json
import argparse
from datetime import datetime

# ==========================================
# 1. UNIVERZÁLNÍ KONFIGURACE
# ==========================================
# Textové soubory, které chceme číst, zbytek indexujeme pouze jako binární
TEXT_EXTENSIONS = {'.txt', '.md', '.csv', '.json', '.py', '.html', '.log'} 
# Všechno ostatní se bude indexovat jako binární/ostatní

ENCODINGS = ['utf-8', 'utf-8-sig', 'cp1250', 'latin-1']

EXCLUDE_DIRS = {
    "Repozitar_Dev", "Archive", "Archive_misc", "Install", 
    "Images", "Foto", "FV_foto", "JK_logs", "solcast_data", 
    "__pycache__", ".git", ".venv"
}

# Filtrování specifických systémových/cache souborů a extenzí
EXCLUDE_FILES = {"desktop.ini"}
EXCLUDE_EXTENSIONS = {".sqlite", ".sqlite3", ".db"}

# Zpřesněná taxonomie pro sémantickou analýzu
TAXONOMY_RULES = {
    "llm_session_history": r"(session\d{3}|claude_session|gemini_session|grok_session|gpt_session)",
    "llm_knowledge_base": r"(deterministic_llm|prompt_json|cli_prompting|transformace_promptu|llm_modely_dev|struktura_knowledgebase)",
    "source_code_python": r"(\.py$|def |import |class )",
    "rag_index_metadata": r"(rag_index|notebooklm_index|master_index|kategorizace_report|migration_dryrun)",
    "data_mining_targets": r"(categories\.csv|topics\.csv|cile_sklizne|ontologie|transfer_dump)",
    "iot_hw_a_fotovoltaika": r"(outpost_2026_datasheet|fv_ingest|lfp_health|bms_|solcast|soc_predict|iot_dev|jk_log)",
    "geodata_a_teren": r"(cut_and_fill|geodata|terrain_profile|horizon_profile|solar_obstacles|drahanske_udoli)",
    "cloud_infrastructure": r"(gcp_stack|cloud_shell|dockerfile|requirements\.txt|ingest_watchdog)",
    "dev_post_mortem": r"(pitevni_kniha|error_gemini|debug_postmortem)",
    "dev_guidelines": r"(standardy_dev_ai|profil_operatora|report_architektura|dred_core_profil)",
    "eshop_produkty": r"(gme_produkty|hornbach_produkty|jacer_produkty|neven_produkty|vrabec_produkty)",
    "diagnostika_a_logy": r"(diagnoza_|detaillogs|bms_log|bms_checkpoint|bms_cleaning|log_cleaned)",
    "dokumentace_master": r"(master\.md|master_inventory\.md)",
    "obecne_texty": r"(\.txt$)",
    "obrazky_a_media": r"(\.png$|\.jpg$|\.jpeg$|\.laz$)",
    "archivy_zip": r"(\.zip$|\.rar$)"
}

# ==========================================
# 2. ROBUSTNÍ STAVEBNÍ BLOKY
# ==========================================

def read_file_safely_and_fix_encoding(file_path: pathlib.Path, bytes_limit: int | None = 4096) -> tuple[str | None, str | None]:
    """Bezpečné čtení souboru s kaskádovým dekódováním a auto-konverzí cp1250 na utf-8."""
    for enc in ENCODINGS:
        try:
            with open(file_path, 'r', encoding=enc, errors='strict') as f:
                content = f.read() if bytes_limit is None else f.read(bytes_limit)
                
                # Pokud detekujeme CP1250 u txt souboru, pokusíme se ho rovnou přeuložit jako UTF-8
                if enc == 'cp1250' and file_path.suffix.lower() == '.txt':
                    try:
                        # Přečteme pro jistotu celý soubor, abychom nezapsali jen snippet
                        with open(file_path, 'r', encoding='cp1250') as f_full:
                            full_content = f_full.read()
                        with open(file_path, 'w', encoding='utf-8') as f_out:
                            f_out.write(full_content)
                        # Pokud to projde, vrátíme to jako utf-8
                        enc = 'utf-8 (converted from cp1250)'
                    except Exception:
                        pass # Když selže přepis, nevadí, vrátíme aspoň původní
                
                return content, enc
        except (UnicodeDecodeError, PermissionError):
            continue
    return None, None

def classify_content(filename: str, content: str) -> str:
    """Klasifikace dokumentu podle obsahu a názvu souboru."""
    ct_lower = content.lower()
    fn_lower = filename.lower()

    for doc_type, regex_pattern in TAXONOMY_RULES.items():
        if re.search(regex_pattern, ct_lower):
            return doc_type

    for doc_type, regex_pattern in TAXONOMY_RULES.items():
        if re.search(regex_pattern, fn_lower):
            return doc_type

    return "neklasifikovano"

# ==========================================
# 3. HLAVNÍ RAG MIGRATION PIPELINE
# ==========================================

def run_ingest_index(target_path: str):
    """Hlavní funkce - prochází cílový adresář a vytváří JSON manifest."""
    source_dir = pathlib.Path(target_path).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        print(f"Chyba: Cesta {source_dir} neexistuje nebo není složka.")
        return

    rag_context_dir = source_dir / "_RAG_Metadata"
    rag_context_dir.mkdir(exist_ok=True)
    
    metadata_json_file = rag_context_dir / "02_rag_metadata.json"

    print(f"-> Zahajuji sémantickou indexaci obsahu v: {source_dir}")
    rag_metadata = {
        "index_timestamp": datetime.now().isoformat(),
        "source_directory": str(source_dir),
        "documents": []
    }

    for root, dirs, files in os.walk(source_dir):
        exclude_lower = {d.lower() for d in EXCLUDE_DIRS}
        dirs[:] = [d for d in dirs if d.lower() not in exclude_lower and not d.startswith('_')]
        
        for name in files:
            file_path = pathlib.Path(root) / name
            ext = file_path.suffix.lower()
            
            # Odstranění systémových a cache souborů
            if name.lower() in EXCLUDE_FILES or ext in EXCLUDE_EXTENSIONS:
                continue

            rel_path = str(file_path.relative_to(source_dir))
            
            # --- Indexujeme VŠECHNO ---
            if ext in TEXT_EXTENSIONS:
                content, encoding = read_file_safely_and_fix_encoding(file_path, bytes_limit=4096)
                if content is None:
                    # I když je to text, pokud nejde číst, bereme jako binární
                    content = ""
                    encoding = "binary_unreadble"
                    snippet = f"[{ext.upper()} soubor - nečitelné kódování]"
                else:
                    snippet = content[:200].replace('\n', ' ').strip()
            else:
                content = ""
                encoding = "binary"
                snippet = f"[{ext.upper()} soubor - obsah nelze číst napřímo]"

            # Klasifikace
            doc_type = classify_content(file_path.name, content)

            rag_metadata["documents"].append({
                "file_path": rel_path,
                "document_type": doc_type,
                "encoding": encoding,
                "size_bytes": file_path.stat().st_size,
                "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                "content_snippet": snippet
            })

    metadata_json_file.write_text(json.dumps(rag_metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print("-" * 50)
    print("HOTOVO!")
    print(f"Sémantická RAG databáze: {metadata_json_file}")
    print(f"Oindexováno souborů: {len(rag_metadata['documents'])}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Univerzální sémantický indexer pro RAG migraci.")
    parser.add_argument("path", help="Absolutní cesta ke složce (např. C:\\Users\\Uzivatel\\Documents)")
    args = parser.parse_args()
    
    run_ingest_index(args.path)
