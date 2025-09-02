# Changelog

Alle wichtigen Änderungen an diesem Projekt werden hier chronologisch dokumentiert.  
Das Format folgt [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), und wir verwenden Semantic Versioning.

## [Unreleased]
### Added
- Job-Log-Tab.
- KI-basierte Tagging/Summarize Option (experimentell).
- Initialisierung einer Tab-Option „Chunk-Ordner nach Merge löschen“.
- Dreispalten-Layout als Alternative zu Tabs (Konvertieren | Auto-Watch | Hilfe).
- Verbesserte Preview & Download-Funktion im Convert-Tab.
- Repair-Tab zur Überprüfung und Korrektur von Markdown-Dateien (inkl. Tabellenfix, Bildpfade, Leerzeilen, YAML-Tags).
- Checkbox-Option in der Sidebar: Nach Erfolg Datei aus `data/in` löschen.
- Erweiterungen in repair_tools.py: Heading-Normalisierung (H1…H6 konsistent, keine Sprünge).
- Erweiterungen in repair_tools.py: Listen-Fix (gemischte -/*/1.-Listen glätten, Einrückung korrigieren).
- Erweiterungen in repair_tools.py: Codeblöcke schließen (offene ``` erkennen/schließen).
- Erweiterungen in repair_tools.py: Link-/Bild-Validation (404 in Assets melden).
- Erweiterungen in repair_tools.py: TOC-Regeneration zwischen Markern (optional).
- Erweiterungen in repair_tools.py: Sprach-Checks (deutsche typografische Anführungszeichen).
- Erweiterungen in repair_tools.py: Frontmatter-Template (author, course, semester, topic, assets_dir).
- UI-Optionen im Repair-Tab: TOC-Regeneration, deutsche Anführungszeichen, Frontmatter-Felder, Assets-Basispfad.

### Changed
- merge_chunk_output(...): Asset-Kopiervorgang auf rekursiv (os.walk) umgestellt, Dateiendungen erweitert (png|jpg|jpeg|webp|gif|svg|tif|tiff|bmp|heic|avif), Kollisionen mit Suffixen (_1, _2, …) abgefangen, Link-Umschreibung beibehalten.
- merge_chunk_output(...): Rückgabewert erweitert & Zählung hinzugefügt.
- convert_marker_chunked(...): Report übernommen.
- UI: Asset-Kopierbericht im Konvertieren-Tab ergänzt.
- UI: Asset-Kopierbericht im Watcher-Tab ergänzt.
- Marker-Fehlerbehandlung verbessert (stderr-Ausgabe sichtbar).
- Heuristik dokumentiert.
- Merge-Logik für Marker-Chunks: robustere Asset-Kopie (Fallback auf Chunk-Root) und Link-Rewrite auch für einfache Dateinamen.
- Chunking standardmäßig immer aktiv (Threshold = 0).
- Merge-Tab erweitert: Ausgabename für finale Markdown-Datei kann frei gewählt werden (anstelle des Slugs).
- Repair-Tab unterstützt manuelles Hinzufügen von YAML-Tags und automatische Korrekturen.
- Delete-after-success Funktion in separater Datei (`housekeeping.py`) gekapselt und in app.py integriert.
- app.py: Repair-Funktion vollständig ausgelagert nach repair_tools.py, nur Import und UI verbleiben.
- app.py: Repair-Tab UI erweitert mit neuen Optionen und Übergabe an load_markdown_and_repair.

### Fixed
- `--verbose`/`--device` aus Marker CLI-Argumenten entfernt, um Laufzeitfehler zu vermeiden.
- Progress-Logs von Marker werden nicht mehr in finale MD-Dateien geschrieben (Trennung stdout/stderr).
- Assets werden korrekt in `./assets/` kopiert und mit Präfix versehen.
- Sanity-Check im Marker-Workflow verhindert leere oder fehlende `.md`-Dateien (klarer Fehlerhinweis mit Empfehlungen).

## [0.8.0] - 2025-08-21
### Added
- Automatisches Chunking für PDFs > 100 Seiten.
- Merge-Tab zur Zusammenführung mehrerer Markdown-Dateien.
- Chunk-Cleanup: Optionale Löschung temporärer Chunk-Verzeichnisse nach Merge.

### Changed
- Automatisches Zusammenführen der Chunks zu einer einzigen Markdown-Datei (mit TOC und Chunk-Überschriften).
- Post-processing erweitert: Entfernt Seitenzahlen, Footer, wiederholte Header; verbessert Leerzeilen/Nutzung.
- UI überarbeitet: Chunking erfolgt heuristisch, ohne sichtbare Checkbox im Sidebar.

### Removed
- Alte Chunking-UI-Toggle aus Sidebar entfernt (ersetzt durch automatische Heuristik).

## [0.7.0] - 2025-08-10
### Added
- `convert_marker_cli` neu gestaltet mit Fallback und Fehler-Handling.
- Debug-Logs & Live-Logging jetzt sichtbar im UI.
### Fixed
- Indentation- und Blockstruktur im Convert-Tab korrigiert.

## [0.6.0] - 2025-07-30
### Added
- HARTE Docker-Härtung inkl. non-root-User, Healthchecks, Python/ OCR-Stapel.
### Changed
- Dockerfile optimiert; command-String & Healthcheck ergänzt.

...

## [0.1.0] - 2025-06-01
### Added
- Erstversion—Basisidee: Automatisierte Umwandlung in Markdown mit Docker + Streamlit.