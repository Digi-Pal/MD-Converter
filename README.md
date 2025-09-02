# Doc → Markdown Converter

Ein schlankes, autonomes Tool  das Dokumentenformate (u.a. PDFs, PPTX, DOCX und reine Textdateien) zuverlässig in Markdown überführt — inklusive Chunking, OCR, Post-Processing und Merge-Funktionalität.

---

##  Inhalt

- Motivation 
- Features
- Schnellstart
- Setup & Installation
- Benutzung
- Architektur
- Engines & Heuristik
- Konfiguration
- Troubleshooting
- Roadmap
- Lizenz / Compliance
- Beitragen
- Danksagung

---

## Motivation
- **Effiziente Digitalisierung deiner Unterlagen**  
  Automatische Konvertierung in Markdown ohne manuelle Nacharbeit.

- **Nahtlose Integration ins Second Brain & RAG-Workflows**  
  Markdown macht Inhalte strukturierbar, durchsuchbar und KI-freundlich.

- **Robustheit bei großen Dokumenten**  
  Automatisches Chunking bei PDFs über 100 Seiten, zuverlässig und stabil.

- **Qualitätsoptimiert durch Post-Processing**  
  Entfernt überflüssige Elemente wie Seitenzahlen oder doppelte Header, korrigiert Bildpfade, optimiert Layout.

- **Modularer Aufbau zum Kombinieren von Inhalten**  
  Merge-Tab bietet flexible Zusammenführung, Inhaltsverzeichnis und Headline-Optionen.

- **Datenschutz & KI-Potenzial**  
  Lokal nutzbar ohne Cloud; Markdown strukturnah für KI–Tagging und semantische Analyse.

- **Open Source & Erweiterbar**  
  Transparent, modular und anpassbar. Ideal für individuelle Workflows.

---

## Features

- **Auto-Chunking großer PDFs (> 100 Seiten)**  
  Sichere Verarbeitung auch umfangreicher Dokumente.

- **Typabhängige Engine-Auswahl (Marker, pptx2md, MarkItDown, Docling)**  
  Für bestmögliche Ergebnisse je Dateityp.

- **Live-Logs & Job-Logging**  
  Echtzeit-Updates während Konvertierung und CSV-Export aller Jobs für späteres Reporting.

- **Post-Process Cleaning**  
  Leseoptimiertes Markdown, für Menschen und Maschinen aufbereitet.

- **Merge-Tab für Markdown-Zusammenführung**  
  TOC, Überschriften und Frontmatter flexibel steuerbar.

- **Docker-basiert & Plattform-agnostisch**  
  Einfach einrichten, überall lauffähig.

- **Streamlit-UI mit klaren Tabs**  
  Einfach zwischen Konvertieren, Auto-Watch, Merge, Job-Log und Hilfe navigieren.

- **Ideal für PKM und KI-Workflows**  
  Strukturierter Inhalt als Basis für KI-Summarization, semantische Suche, Wissensgraphen.

- **Docker-Hardening:**
  Non-root, ffmpeg, Tesseract (deu/eng), Poppler, qpdf, Ghostscript; Torch CPU-Wheels.

- **Streamlit-UI mit Tabs:** 
  Konvertieren · Auto-Watch · Merge · Job-Log · Hilfe. 

- **Auto-Engine-Auswahl:** 
  Marker/Docling/MarkItDown/pptx2md nach Dateityp; manuelles Override möglich. 

- **PPTX-Pfad (pptx2md):** 
  Klarere Slides & Bild-Export. 

- **OCR-Varianten in Docling:**
  auto / easyocr / tesseract / rapidocr (optional ocrmypdf). 

- **Post-Processing:**
  relative Bildpfade ./assets/..., leichte Tabellenhygiene, optionale Dateinameingabe statt index.md. 

- **Batch-Watcher:**
  verarbeitet data/in automatisch; Status & CSV-Joblog. 

- **Merge-Tab:** 
  mehrere Markdown-Dateien zusammenführen (Titel als H2, TOC, Frontmatter-Strip, Trenner). 

- **Docker-Hardening:**
  Non-root, ffmpeg, Tesseract (deu/eng), Poppler, qpdf, Ghostscript; Torch CPU-Wheels.

---

## Setup & Installation

### Ordnerstruktur (host)
```csharp
md-converter/
├─ docker-compose.yml
├─ Dockerfile
├─ app.py
└─ data/
   ├─ in/     # Eingaben
   └─ out/    # Ergebnisse (MD + assets) – direkt Obsidian-tauglich
````
### Docker Compose (Ausschnitt)
```yaml
services:
  converter:
    build: .
    container_name: md-converter
    ports: ["8501:8501"]
    volumes:
      - ./data/in:/app/data/in
      - ./data/out:/app/data/out
      - ./data/cache:/app/.cache   # Modelle/Fonts persistent
    command: >
      streamlit run /app/app.py --server.port 8501 --server.address 0.0.0.0
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8501').status==200 else sys.exit(1)\""]
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 20s
```

### Dockerfile (Kernideen)
- Systempakete: ffmpeg, tesseract-ocr (+ -deu, -eng), poppler-utils, qpdf, ghostscript, Python: markitdown[all], marker-pdf[full], docling, pptx2md, streamlit, watchdog, OCR-Stacks (easyocr, rapidocr-onnxruntime, ocrmypdf), Torch (CPU Wheels)
- Non-root User, vorbereitete Cache-Verzeichnisse & Marker-Fonts

### Voraussetzungen
- Docker + `docker-compose`

### Erste Schritte

1. Repository klonen:
```bash
git clone <dein-repo-url>
cd md-converter
```

2.	Build & Start der App:
```bash
docker compose up --build
```

3.	Weboberfläche öffnen: http://localhost:8501

## Benutzung
1.	Konvertieren-Tab: Einzel- oder Batch-Konvertierung:
- Dateien hochladen
-	Automatischer Chunking (bei PDFs >100 S.)
-	Optional Frontmatter hinzufügen
-	Vorschau anzeigen & Download möglich
2.	Auto-Watch-Tab: Überwacht data/in und konvertiert automatisch neue Dateien.
3.	Merge-Tab: Wandle mehrere Markdown-Dateien
-	Headline, Inhaltsverzeichnis, Frontmatter entfernen optional
-	Download-File wird generiert + Vorschau angezeigt
4.	Job-Log-Tab: Zeigt vollständiges Protokoll aller Konvertierungen und Merges; Export als CSV möglich.


## Technologie & Architektur
```mermaid
flowchart LR
A[Upload / data/in] --> B{Engine wählen}
B -->|PDF (gescannt/komplex)| M[Marker / Docling]
B -->|PPT/PPTX| P[pptx2md]
B -->|DOCX/HTML| K[MarkItDown]
B -->|TXT| T[Plain 1:1]
M --> C[Post-Processing]
P --> C
K --> C
T --> C
C --> D[Frontmatter + rel. Assets]
D --> E[data/out/<slug>/<name>.md]
E --> F[[Obsidian Vault]]
```
- Streamlit UI: Klare Tabs und Live-Updates.
- Marker / Docling / pptx2md: Fokussierte Engines für Dateitypen.
- Docker-Container: Alle Dependencies sicher und wiederholbar.
- Funktionale Systemlogik:
- Chunking-Helper (get_pdf_page_count, chunk_pdf, merge_chunk_output)
- Post-Processing mit Regex-Aufräumen
- Merge-Engine mit TOC & optionalen Überschriften
- Logging als CSV-getrackerte Historie

## Engines & Heuristik
Dateityp / Szenario	Empfehlung	Anmerkung
Wissenschaftliche/komplexe PDFs	Docling oder Marker	Layout/Tabellen/Formeln stark; Marker CLI marker_single nutzt OCR/Layouts. 
Reine Präsentationen	pptx2md	Klare Slide-Struktur, Bild-Export. 
Gemischte Bestände (DOCX/HTML)	MarkItDown	Allrounder, simple API. 
TXT	Plain	1:1 in Markdown, optional Frontmatter. 
OCR-Auswahl (Docling): auto / easyocr / tesseract / rapidocr (optional ocrmypdf Pre-OCR).

## Konfiguration & Erweiterung
- Chunk-Schwelle: Anpassen über AUTO_CHUNK_THRESHOLD im Code.
- Erweiterung:
    - Rückfall-Engine ändern (z. B. KI-Zusammenfassung hinzufügen)
    - ORC-Engine austauschen (EasyOCR, Tesseract, RapidOCR)
    - Merge mit eigenen Regeln erweitern (Templates, Frontmatter-Merge)
    - Dockerfile & Compose: Einfach optimierbar für CI, GitHub Actions, oder Nutzung in Schulen.
- Ausgabename (statt index.md) via Sidebar; Output: ./data/out/<slug>/<dein_name>.md. 
- Post-Processing: relative Bildpfade ./assets/..., sanfte Tabellenhygiene. 
- Watcher-Intervall: Slider in UI; Polling-Variante docker-freundlich. 
- Persistente Caches/Modelle: Volume-Mount ./data/cache:/app/.cache. 
- Healthcheck: prüft :8501 (Streamlit) in Compose. 
### Optionale LLM-Integration (lokal, DSGVO-freundlich):
- Ollama auf dem Host (http://host.docker.internal:11434) für Summary + Tags; JSON-Merge ins Frontmatter, Fallback-sicher.

## Troubleshooting
marker_single bricht ab (Exit 1)
**Typische Ursachen:** fehlende Weights/Netz, defektes/verschlüsseltes PDF, OCR-Edgecases, Output-Rechte. 

Prüfen im Container:
```bash
docker exec -it md-converter bash
marker_single "/app/data/in/<datei>.pdf" --output_format markdown --output_dir /app/data/out/test
# ggf. mit --force_ocr
```

*(Hinweis: --device/--verbose sind keine gültigen Marker-Flags – Logs über stderr ansehen.)* 

- ffmpeg-Warnung
  - Mit ffmpeg im Image beseitigt. 
- OCR ungenau
  - In der Sidebar OCR-Variante wechseln (EasyOCR ↔ Tesseract ↔ RapidOCR) bzw. optional ocrmypdf vorschalten.

## Contribution & Zusammenarbeit
- Beiträge willkommen! Einfach Fork, Branch, Pull-Merge.
- Issues für Vorschläge oder Bugs open.
- Workshop-Ideas: bessere Konfiguration, erweiterbare Engines, Sync mit Obsidian-Vorlagen.

## Lizenz
Dieses Projekt wird unter der GNU GENERAL PUBLIC LICENSE Version 3 veröffentlicht - offen, frei adaptierbar mit Copyleft-Schutz.

## Credits & Danksagung
- Initator: Patrick / Digi-Pal : Dein Digitaler Kollege
- Tools / Engines: Dank an Autoren von Marker, Docling, MarkItDown, pptx2md, Streamlit

---
> **Hinweis:** Teile dieser Dokumentation und Projektstruktur wurden mit **KI-Unterstützung** (ChatGPT by OpenAI) generiert und anschließend redaktionell geprüft und angepasst.
---
