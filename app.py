# Dieser Code wurde unter Verwendung von generativer KI (OpenAI ChatGPT) generiert, geprüft und handbearbeitet.
import os, io, shutil, time, subprocess, tempfile, re, json, csv
from datetime import datetime
import streamlit as st

# Import hier, damit Container schneller buildet (und App schneller lädt)
from markitdown import MarkItDown
from docling.document_converter import DocumentConverter

IN_DIR  = "/app/data/in"
OUT_DIR = "/app/data/out"
AUTO_CHUNK_THRESHOLD = 0  # immer chunken: jedes PDF mit >=1 Seite wird gechunkt

os.makedirs(IN_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

st.set_page_config(page_title="Doc → Markdown Converter", layout="centered")
st.title("Doc → Markdown (MarkItDown · Docling · Marker)")

# Repair-Tools werden aus separater Datei geladen (keine Fallback-Implementierung in app.py)
try:
    from repair_tools import load_markdown_and_repair  # def load_markdown_and_repair(md_text:str, extra_tags:list[str], ...) -> str
except Exception as e:
    def load_markdown_and_repair(*args, **kwargs):
        raise RuntimeError(f"repair_tools.py nicht gefunden oder fehlerhaft: {e}")

try:
    from housekeeping import delete_from_inbox  # def delete_from_inbox(path:str) -> None
except Exception:
    def delete_from_inbox(path: str) -> None:
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

tab_convert, tab_watch, tab_repair, tab_merge, tab_joblog, tab_help = st.tabs(["Konvertieren", "Auto-Watch", "Repair", "Merge", "Job-Log", "Hilfe"])
with tab_help:
    st.subheader("Hilfe & Quickstart")
    st.markdown("""
**Schnellstart**
1. Datei(en) hochladen → **Konvertieren** drücken  
2. Optional **Ausgabename** setzen (sonst verwenden wir den *slug*).  
3. Ergebnis-Ordner `./data/out/<slug>/` in Obsidian übernehmen.

**Engine-Empfehlung**  
- PDF → *Marker* (beste Qualität)  
- PPTX → *pptx2md* (saubere Folienstruktur)  
- DOCX/HTML → *MarkItDown*  
- Fallback → *Docling*

**Troubleshooting**  
- ffmpeg-Warnung ist durch Installation behoben.  
- OCR-Qualität unzureichend? In der Sidebar *Docling OCR* wechseln (auto/easyocr/tesseract/rapidocr).
""")

with st.sidebar:
    st.header("Einstellungen")
    engine = st.selectbox("Engine", ["Auto", "MarkItDown", "Docling", "Marker", "pptx2md"])
    add_frontmatter = st.checkbox("Obsidian Frontmatter hinzufügen", value=True)
    tags_default = st.text_input("Standard-Tags (kommagetrennt)", "studium,import")
    output_name = st.text_input("Ausgabename (ohne .md, optional)", "")
    force_ocr = st.checkbox("OCR forcieren (Marker)", value=False)
    keep_images = st.checkbox("Bilder extrahieren", value=True)
    ocr_engine = st.selectbox("Docling OCR", ["auto", "easyocr", "tesseract", "rapidocr"], index=0)
    enable_watcher = st.checkbox("Auto-Watch: data/in überwachen", value=False)
    watch_interval = st.number_input("Watch-Intervall (Sek.)", min_value=2, max_value=120, value=10, step=1)
    live_marker_logs = st.checkbox("Live-Logs (Marker) anzeigen", value=True, help="Zeigt Marker-Ausgabe (stdout/stderr) während der Konvertierung live an.")
    chunk_size = st.number_input("Chunk-Größe (Seiten)", min_value=10, max_value=100, value=20, step=5)
    cleanup_chunks = st.checkbox("Chunk-Ordner nach Merge löschen", value=True, help="Temporäre _chunk_XX-Verzeichnisse werden nach dem Zusammenführen entfernt.")
    delete_after_success = st.checkbox("Nach Erfolg: Datei aus data/in löschen", value=False)

if output_name and not re.match(r"^[\w\- ]+$", output_name):
    st.warning("Ausgabename: Erlaubt sind Buchstaben, Zahlen, Unterstrich und Bindestrich.")

def slugify(name: str) -> str:
    base = os.path.splitext(os.path.basename(name))[0]
    base = re.sub(r"[^\w\-]+","-", base.lower()).strip("-")
    return base or f"doc-{int(time.time())}"

def write_frontmatter(md_text: str, title: str, src_name: str, tags: list[str]) -> str:
    fm = {
        "title": title,
        "source_file": src_name,
        "imported_at": datetime.now().isoformat(timespec="seconds"),
        "tags": tags
    }
    return f"---\n{json.dumps(fm, ensure_ascii=False, indent=2)}\n---\n\n{md_text}"

def postprocess_markdown(md_text: str, assets_rel="./assets") -> str:
    # 1) Bildpfade relativieren
    md_text = re.sub(
        r'!\[(.*?)\]\((?:\./)?(?:assets/)?([^\)\s]+)\)',
        lambda m: f"![{m.group(1)}]({assets_rel}/{m.group(2)})",
        md_text,
    )

    # 2) Zeilenweise Reinigung (Seitenzahlen, häufige Footer/Köpfe)
    lines = md_text.splitlines()
    cleaned = []
    freq = {}
    for ln in lines:
        key = ln.strip()
        if 0 < len(key) <= 60:
            freq[key] = freq.get(key, 0) + 1

    def looks_like_footer(s: str) -> bool:
        s_low = s.strip().lower()
        # reine Seitenzahlen
        if re.match(r"^\d{1,4}$", s_low):
            return True
        # Seite X / Seite X von Y / Page X / Page X of Y
        if re.match(r"^(seite|page)\s+\d+(\s+(von|of)\s+\d+)?$", s_low):
            return True
        return False

    repeated = {s for s, c in freq.items() if c >= 5 and looks_like_footer(s)}

    for ln in lines:
        raw = ln.rstrip()
        key = raw.strip()
        if key and (key in repeated or looks_like_footer(key)):
            continue
        if "|" in raw:
            raw = re.sub(r" {2,}", " ", raw)
        cleaned.append(raw)

    md_text = "\n".join(cleaned)

    # 3) Doppelte Leerzeilen normalisieren
    md_text = re.sub(r"\n{3,}", "\n\n", md_text)

    return md_text


# Helper: Entfernt YAML-Frontmatter am Dokumentanfang, falls vorhanden.
def strip_frontmatter(md: str) -> str:
    """Entfernt YAML-Frontmatter am Dokumentanfang, falls vorhanden."""
    if md.lstrip().startswith("---"):
        lines = md.splitlines()
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    return "\n".join(lines[i+1:]).lstrip("\n")
    return md

def log_job(row: dict):
    logfile = "/app/data/joblog.csv"
    file_exists = os.path.exists(logfile)
    # Sichere Feldreihenfolge
    keys = ["timestamp","source","engine","ocr","duration_ms","output_path","status","error"]
    for k in keys:
        if k not in row:
            row[k] = ""
    with open(logfile, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        if not file_exists:
            w.writeheader()
        w.writerow(row)

def read_joblog_last(n: int = 10):
    logfile = "/app/data/joblog.csv"
    if not os.path.exists(logfile):
        return []
    with open(logfile, "r", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        rows = list(r)
    if not rows:
        return []
    return rows[-n:][::-1]

def convert_markitdown(path: str) -> str:
    md = MarkItDown()
    res = md.convert(path)
    return res.text_content

def convert_docling(path: str) -> str:
    # Docling nutzt intern Converter-Pipelines; wir schalten über env/flags grob um
    from docling.document_converter import DocumentConverter
    from docling.datamodel.base_models import ConversionResult

    # Primitive Umschaltung: Wir setzen ENV-Flags, die du im Container kontrollierst
    # und die Docling-Pipelines (oder deine eigenen) auslesen können.
    # Fallback: Wir probieren, ohne OCR zu konvertieren und nutzen nur bei Bedarf OCR.
    want_ocr = os.path.splitext(path)[1].lower() in [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"]

    # Vor-OCR für Tesseract via ocrmypdf (optional, falls installiert)
    if ocr_engine == "tesseract" and want_ocr:
        try:
            import shutil, tempfile, subprocess
            tmp_pdf = path
            if path.lower().endswith(".pdf"):
                ocr_out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
                subprocess.run(["ocrmypdf", "--skip-text", path, ocr_out, "--optimize", "0"], check=True)
                tmp_pdf = ocr_out
            # Danach normale Konvertierung auf OCR-PDF
            conv = DocumentConverter()
            return conv.convert(tmp_pdf).document.export_to_markdown()
        except Exception as _:
            # Fallback: normale Konvertierung
            pass
    # EasyOCR / RapidOCR – hier verlassen wir uns auf Docling-Defaults
    # (EasyOCR ist typischer Default; RapidOCR aktiviert Docling i. d. R., wenn vorhanden)
    conv = DocumentConverter()
    result: ConversionResult = conv.convert(path)
    return result.document.export_to_markdown()

def convert_pptx2md(path: str, out_dir: str) -> str:
    # legt Bilder im Ordner an; schreibt stdout als MD
    import subprocess, os
    assets = os.path.join(out_dir, "assets")
    os.makedirs(assets, exist_ok=True)
    # --img-dir legt das Ziel für exportierte Bilder fest
    res = subprocess.run(
        ["pptx2md", path, "--img-dir", assets],
        check=True, capture_output=True, text=True
    )
    return res.stdout


def _marker_advice(force_ocr: bool, keep_images: bool) -> str:
    tips = [
        "Prüfe, ob das PDF passwortgeschützt oder beschädigt ist.",
        f"Schalte OCR {'aus' if force_ocr else 'ein'} (Option „OCR forcieren“) und versuche es erneut.",
        "Setze die Chunk-Größe kleiner (z. B. 10–15 Seiten).",
        "Lass testweise Bilder-Extraktion an, falls Layout-Analyse an Bilder gebunden ist.",
        "Teste die gleiche Datei einmal mit Docling (Engine „Docling“), um ein Datei- oder Parserproblem auszuschließen.",
    ]
    if not keep_images:
        tips.append("Hinweis: Bilder-Extraktion ist deaktiviert – das ist ok, kann aber die Layout-Erkennung beeinflussen.")
    return "- " + "\n- ".join(tips)

def convert_marker_cli(path: str, out_dir: str, force_ocr: bool, keep_images: bool, live_cb=None) -> tuple[str, str]:
    """
    Runs marker_single and returns (markdown_text, debug_log).
    On failure, tries a fallback run toggling --force_ocr.
    Raises RuntimeError with combined stderr if both attempts fail.
    live_cb: optional callback(line:str) for live logs.
    """
    def _run_marker(_force_ocr: bool) -> tuple[bool, str, str]:
        args = [
            "marker_single",
            path,
            "--output_format", "markdown",
            "--output_dir", out_dir,
        ]
        if _force_ocr:
            args.append("--force_ocr")
        if not keep_images:
            args.append("--disable_image_extraction")

        if callable(live_cb):
            # Stream live output
            proc = subprocess.Popen(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
            collected = []
            try:
                for line in proc.stdout:
                    collected.append(line.rstrip("\n"))
                    live_cb(line.rstrip("\n"))
            finally:
                proc.wait()
            ok = proc.returncode == 0
            return ok, "\n".join(collected), ""  # stderr gemerged in stdout
        else:
            # capture stdout/stderr to show in UI
            proc = subprocess.run(args, text=True, capture_output=True)
            ok = proc.returncode == 0
            return ok, proc.stdout, proc.stderr

    # First attempt
    ok1, out1, err1 = _run_marker(force_ocr)
    if ok1:
        # Pick newest .md from out_dir (recursive)
        md_candidates = []
        for root, _dirs, files in os.walk(out_dir):
            for n in files:
                if n.lower().endswith(".md"):
                    md_candidates.append(os.path.join(root, n))
        if not md_candidates:
            raise RuntimeError(
                "Marker hat keine Markdown-Datei erzeugt.\n\nLogs:\n" + (err1 or out1 or "(keine Logs)") +
                "\n\nEmpfehlungen:\n" + _marker_advice(force_ocr, keep_images)
            )
        md_candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        with open(md_candidates[0], "r", encoding="utf-8") as fh:
            md_text = fh.read()
        # Sanity check: empty or trivially short output is suspicious
        if not md_text or len(md_text.strip()) < 50:
            raise RuntimeError(
                "Sanity check fehlgeschlagen: Marker hat eine ungewöhnlich kurze Markdown-Datei erzeugt.\n\n"
                "Empfehlungen:\n" + _marker_advice(force_ocr, keep_images)
            )
        return md_text, err1 or ""

    # Fallback attempt: toggle force_ocr
    ok2, out2, err2 = _run_marker(not force_ocr)
    if ok2:
        md_candidates = []
        for root, _dirs, files in os.walk(out_dir):
            for n in files:
                if n.lower().endswith(".md"):
                    md_candidates.append(os.path.join(root, n))
        if not md_candidates:
            raise RuntimeError(
                "Marker (Fallback) hat keine Markdown-Datei erzeugt.\n\nErster Lauf:\n{}\n\nFallback-Logs:\n{}\n\nEmpfehlungen:\n{}".format(
                    err1 or "(keine Logs)", err2 or "(keine Logs)", _marker_advice(force_ocr, keep_images)
                )
            )
        md_candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        with open(md_candidates[0], "r", encoding="utf-8") as fh:
            md_text = fh.read()
        # Sanity check: empty or trivially short output is suspicious
        if not md_text or len(md_text.strip()) < 50:
            raise RuntimeError(
                "Sanity check fehlgeschlagen: Marker hat eine ungewöhnlich kurze Markdown-Datei erzeugt.\n\n"
                "Empfehlungen:\n" + _marker_advice(force_ocr, keep_images)
            )
        return md_text, (err1 or "") + "\n" + (err2 or "")

    # Both failed: raise with combined logs
    combined = "First attempt (force_ocr={}):\n{}\n\nFallback (force_ocr={}):\n{}".format(
        force_ocr, err1 or out1 or "(no logs)", not force_ocr, err2 or out2 or "(no logs)"
    )
    raise RuntimeError("Marker failed on both attempts.\n\n" + combined + "\n\nEmpfehlungen:\n" + _marker_advice(force_ocr, keep_images))


def convert_marker_chunked(src_pdf: str, target_dir: str, force_ocr: bool, keep_images: bool, chunk_size: int, live_cb=None, cleanup: bool = False) -> tuple[str, str]:
    """
    Verarbeitet ein PDF in Chunks mit Marker. Fällt pro Chunk auf Docling zurück.
    Gibt (merged_markdown, combined_logs) zurück.
    """
    md_parts: list[tuple[str, tuple[int,int]]] = []
    chunk_assets_dirs: list[str] = []
    logs = []
    chunk_dirs: list[str] = []

    chunks = chunk_pdf(src_pdf, chunk_size)
    for idx, (tmp_pdf, (start, end)) in enumerate(chunks, start=1):
        chunk_out = os.path.join(target_dir, f"_chunk_{idx:02d}")
        os.makedirs(chunk_out, exist_ok=True)
        chunk_dirs.append(chunk_out)
        try:
            md_text, mk_logs = convert_marker_cli(tmp_pdf, chunk_out, force_ocr, keep_images, live_cb=live_cb)
            logs.append(f"[chunk {idx} {start}-{end}] MARKER ok")
            if mk_logs:
                logs.append(mk_logs)
        except Exception as e:
            logs.append(f"[chunk {idx} {start}-{end}] MARKER failed: {e}")
            try:
                md_text = convert_docling(tmp_pdf)
                logs.append(f"[chunk {idx} {start}-{end}] DOCLING ok")
            except Exception as e2:
                logs.append(f"[chunk {idx} {start}-{end}] DOCLING failed: {e2}")
                raise RuntimeError("\n".join(logs))
        # Determine asset source for this chunk: prefer <chunk>/assets, otherwise the chunk root
        src_assets = os.path.join(chunk_out, "assets") if os.path.isdir(os.path.join(chunk_out, "assets")) else chunk_out
        chunk_assets_dirs.append(src_assets)
        md_parts.append((md_text, (start, end)))

    merged_md, assets_report = merge_chunk_output(md_parts, os.path.join(target_dir, "assets"), chunk_assets_dirs)
    if assets_report:
        logs.append(assets_report)
        # Optional: temporäre Chunk-Ordner entfernen
        if cleanup:
            for d in chunk_dirs:
                try:
                    shutil.rmtree(d, ignore_errors=True)
                except Exception:
                    pass
        return merged_md, "\n".join(logs)

def convert_plain_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()
def build_page_chunks(total_pages: int, chunk_size: int) -> list[tuple[int,int]]:
    chunks = []
    start = 1
    while start <= total_pages:
        end = min(start + chunk_size - 1, total_pages)
        chunks.append((start, end))
        start = end + 1
    return chunks

def chunk_pdf(src_path: str, chunk_size: int) -> list[tuple[str, tuple[int,int]]]:
    """
    Schneidet src_path in temporäre PDFs mit je chunk_size Seiten.
    Rückgabe: Liste [(temp_pdf_path, (start,end)), ...], 1-basiert.
    """
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(src_path)
    n = len(reader.pages)
    chunks = []
    for (start, end) in build_page_chunks(n, chunk_size):
        writer = PdfWriter()
        for p in range(start, end+1):
            writer.add_page(reader.pages[p-1])
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
        with open(tmp, "wb") as oh:
            writer.write(oh)
        chunks.append((tmp, (start, end)))
    return chunks

def merge_chunk_output(md_parts: list[tuple[str, tuple[int,int]]], final_assets_dir: str, chunk_assets_dirs: list[str]) -> tuple[str, str]:
    """
    md_parts: Liste [(md_text, (start,end)), ...]
    chunk_assets_dirs: parallele Liste mit Pfaden zu den assets-Quellordnern je Chunk
    Kopiert Assets in final_assets_dir, präfixiert Links je Chunk, baut eine TOC pro Chunk und setzt Überschriften.
    """
    os.makedirs(final_assets_dir, exist_ok=True)
    merged = []
    toc = ["## Inhalt (Chunks)"]
    report_lines = []
    for idx, ((md_text, (start, end)), src_assets) in enumerate(zip(md_parts, chunk_assets_dirs), start=1):
        anchor = f"chunk-{idx:02d}-seiten-{start}-{end}"
        heading = f"## Chunk {idx:02d} (Seiten {start}–{end})"
        toc.append(f"- [{heading[3:]}](#{anchor})")

        prefix = f"c{idx:02d}_"
        found_cnt = 0
        copied_cnt = 0
        if os.path.isdir(src_assets):
            # Copy images recursively (Marker kann Unterordner wie images/, figures/ etc. anlegen)
            for root, _dirs, files in os.walk(src_assets):
                for name in files:
                    if re.search(r"\.(png|jpe?g|webp|gif|svg|tif|tiff|bmp|heic|avif)$", name, re.IGNORECASE):
                        found_cnt += 1
                        src = os.path.join(root, name)
                        dst = os.path.join(final_assets_dir, prefix + name)
                        try:
                            shutil.copy2(src, dst)
                            copied_cnt += 1
                        except Exception:
                            base, ext = os.path.splitext(name)
                            k = 1
                            while True:
                                alt = f"{prefix}{base}_{k}{ext}"
                                dst_alt = os.path.join(final_assets_dir, alt)
                                if not os.path.exists(dst_alt):
                                    shutil.copy2(src, dst_alt)
                                    copied_cnt += 1
                                    break
                                k += 1
        # Berichtzeile je Chunk
        report_lines.append(f"[assets] Chunk {idx:02d} {start}-{end}: gefunden={found_cnt}, kopiert={copied_cnt}, quelle='{src_assets}'")

        # Bildlinks im Markdown auf ./assets/ mit Chunk-Präfix umschreiben
        def _rewr_any(m):
            alt, href = m.group(1), m.group(2)
            # Skip external/data/anchor links
            if href.startswith(("http://", "https://", "data:", "#")):
                return m.group(0)
            fname = os.path.basename(href)
            return f"![{alt}](./assets/{prefix}{fname})"
        md_text = re.sub(r'!\[(.*?)\]\(([^)\s]+)\)', _rewr_any, md_text)

        # Abschnitt in den Merge-Container aufnehmen
        merged.append(f"\n\n<a name=\"{anchor}\"></a>\n{heading}\n\n{md_text}")

    merged_text = "\n\n".join(toc) + "\n\n" + "\n\n".join(merged)
    return merged_text, "\n".join(report_lines)

def read_joblog_all():
        logfile = "/app/data/joblog.csv"
        if not os.path.exists(logfile):
            return []
        with open(logfile, "r", encoding="utf-8") as fh:
            r = csv.DictReader(fh)
            return list(r)


# Helper: get page count of a PDF
def get_pdf_page_count(path: str) -> int:
    from pypdf import PdfReader
    try:
        return len(PdfReader(path).pages)
    except Exception:
        return -1

def choose_engine(path: str, engine_choice: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if engine_choice != "Auto":
        return engine_choice
    # Heuristik:
    if ext in [".pdf"]:
        return "Marker"       # sehr gute PDF-Qualität
    if ext in [".ppt", ".pptx"]:
        return "pptx2md"
    if ext in [".txt"]:
        return "plain"
    if ext in [".ppt", ".pptx", ".doc", ".docx", ".xls", ".xlsx", ".html", ".htm", ".epub"]:
        return "MarkItDown"
    # Fallback
    return "Docling"

with tab_convert:
    uploaded = st.file_uploader("Datei(en) hochladen", type=None, accept_multiple_files=True)

    if uploaded and st.button("Konvertieren"):
        for f in uploaded:
            _t0 = time.time()
            # Speichere Upload
            input_path = os.path.join(IN_DIR, f.name)
            with open(input_path, "wb") as out:
                out.write(f.read())

            slug = slugify(f.name)
            # Ausgabename bestimmen
            base_name = output_name.strip() or slug
            target_dir = os.path.join(OUT_DIR, slug)
            assets_dir = os.path.join(target_dir, "assets")
            os.makedirs(target_dir, exist_ok=True)
            os.makedirs(assets_dir, exist_ok=True)

            pick = choose_engine(input_path, engine)
            st.write(f"**{f.name}** → Engine: `{pick}`")
            st.caption(f"Ausgewählte Engine: **{pick}**")

            with st.status(f"Konvertiere **{f.name}** …", expanded=False) as status:
                try:
                    if pick == "MarkItDown":
                        md_text = convert_markitdown(input_path)
                    elif pick == "Docling":
                        md_text = convert_docling(input_path)
                    elif pick == "pptx2md":
                        md_text = convert_pptx2md(input_path, target_dir)
                    elif pick == "plain":
                        md_text = convert_plain_text(input_path)
                    else:  # Marker (CLI)
                        live_lines = []
                        live_area = None
                        def _cb(line: str):
                            live_lines.append(line)
                            if live_area is not None:
                                # Update live text (truncate to last ~200 lines for performance)
                                live_area.code("\n".join(live_lines[-200:]), language="bash")
                        if live_marker_logs:
                            with st.expander("Live-Logs (Marker)", expanded=False):
                                live_area = st.empty()
                        is_pdf = input_path.lower().endswith(".pdf")
                        use_chunk = False
                        if is_pdf:
                            pc = get_pdf_page_count(input_path)
                            if pc != -1 and pc > int(AUTO_CHUNK_THRESHOLD):
                                use_chunk = True
                                st.caption(f"Auto-Chunk aktiv: {pc} Seiten > {int(AUTO_CHUNK_THRESHOLD)} → Chunk-Größe {int(chunk_size)}.")
                        if is_pdf and use_chunk:
                            md_text, marker_logs = convert_marker_chunked(
                                input_path, target_dir, force_ocr, keep_images, int(chunk_size),
                                live_cb=_cb if live_marker_logs else None,
                                cleanup=cleanup_chunks
                            )
                        else:
                            md_text, marker_logs = convert_marker_cli(
                                input_path, target_dir, force_ocr, keep_images,
                                live_cb=_cb if live_marker_logs else None
                            )

                    md_text = postprocess_markdown(md_text, assets_rel="./assets")

                    if add_frontmatter:
                        tags = [t.strip() for t in tags_default.split(",") if t.strip()]
                        md_text = write_frontmatter(md_text, title=slug, src_name=f.name, tags=tags)

                    out_md = os.path.join(target_dir, f"{base_name}.md")
                    with open(out_md, "w", encoding="utf-8") as oh:
                        oh.write(md_text)

                    dur_ms = int((time.time() - _t0) * 1000)
                    st.success(f"Fertig: {out_md} (Assets: {assets_dir}) · {dur_ms} ms")
                    if delete_after_success:
                        try:
                            delete_from_inbox(input_path)
                            st.caption(f"Quelle gelöscht: {input_path}")
                        except Exception:
                            st.caption(f"Konnte Quelle nicht löschen: {input_path}")
                    with st.expander(f"Vorschau: {base_name}.md"):
                        st.markdown(md_text[:8000])
                        st.download_button("Markdown herunterladen", md_text.encode("utf-8"), file_name=f"{base_name}.md")
                    if pick == "Marker":
                        with st.expander("Marker-Umgebung (Cache)"):
                            st.code(
                                "\n".join([
                                    f"HOME={os.environ.get('HOME')}",
                                    f"XDG_CACHE_HOME={os.environ.get('XDG_CACHE_HOME')}",
                                    f"HF_HOME={os.environ.get('HF_HOME')}",
                                    f"HUGGINGFACE_HUB_CACHE={os.environ.get('HUGGINGFACE_HUB_CACHE')}",
                                    f"SURYA_CACHE_DIR={os.environ.get('SURYA_CACHE_DIR')}",
                                ]),
                                language="bash"
                            )
                        with st.expander("Marker-Logs (stderr/stdout)"):
                            st.code(marker_logs or "(keine Logs)", language="bash")
                        with st.expander("Asset-Kopierbericht"):
                            asset_lines = "\n".join([ln for ln in (marker_logs or "").splitlines() if ln.startswith("[assets]")])
                            st.code(asset_lines or "(keine Assets gefunden oder kopiert)", language="bash")    
                    log_job({
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "source": f.name,
                        "engine": pick,
                        "ocr": ocr_engine if pick == "Docling" else "",
                        "duration_ms": dur_ms,
                        "output_path": out_md,
                        "status": "ok",
                        "error": ""
                    })
                    status.update(label="Konvertierung abgeschlossen", state="complete")
                except Exception as e:
                    dur_ms = int((time.time() - _t0) * 1000)
                    st.error(f"Fehler bei {f.name}: {e}")
                    st.info("Tipp: Siehe Empfehlungen oben. Passe ggf. OCR, Chunk-Größe oder Engine an und starte erneut.")
                    with st.expander("Fehlerdetails / Logs"):
                        st.code(str(e), language="bash")
                    log_job({
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "source": f.name,
                        "engine": pick,
                        "ocr": ocr_engine if pick == "Docling" else "",
                        "duration_ms": dur_ms,
                        "output_path": "",
                        "status": "error",
                        "error": str(e)
                    })
                    status.update(label="Fehlgeschlagen", state="error")

    st.info("Outputs liegen unter ./data/out/<slug>/<dein_name>.md (+ assets). Ordner in Obsidian übernehmen.")
    st.caption("Job-Log: /app/data/joblog.csv (timestamp, source, engine, ocr, duration_ms, output_path, status, error)")


# Repair Tab: Markdown prüfen & reparieren
with tab_repair:
    st.subheader("Markdown reparieren")
    st.caption("Lade eine Markdown-Datei, wir prüfen typische Probleme (Tabellen, doppelte Leerzeilen, Bildpfade) und können zusätzliche Tags im Frontmatter ergänzen.")
    rep_file = st.file_uploader("Markdown-Datei wählen", type=["md", "markdown", "txt"], accept_multiple_files=False, key="repair_uploader")
    extra_tags_in = st.text_input("Zusätzliche Tags (kommagetrennt)", "")
    do_fix_tables = st.checkbox("Tabellen reparieren", value=True, help="Pipes normalisieren, Spaltenanzahl angleichen, Separatorzeile sicherstellen.")
    do_fix_images = st.checkbox("Bildpfade relativ auf ./assets setzen", value=True)
    do_trim_blank = st.checkbox("Mehrfache Leerzeilen reduzieren", value=True)
    if rep_file and st.button("Reparieren"):
        raw = rep_file.read().decode("utf-8", errors="ignore")
        tags_list = [t.strip() for t in extra_tags_in.split(",") if t.strip()]
        repaired = load_markdown_and_repair(raw, tags_list)
        if do_fix_images:
            repaired = re.sub(r'!\[(.*?)\]\((?:\./)?(?:assets/)?([^\)\s]+)\)', lambda m: f"![{m.group(1)}](./assets/{m.group(2)})", repaired)
        if do_trim_blank:
            repaired = re.sub(r"\n{3,}", "\n\n", repaired)
        if do_fix_tables:
            # einfache Zweitpass-Normalisierung: Trennzeile prüfen
            repaired = re.sub(r"(\n\|[^\n]+\|\n)(?!\|[ :\-|]+\|\n)", lambda m: m.group(1) + "|" + " --- |"*(max(1, m.group(1).count('|')-1)) + "\n", repaired)
        st.success("Reparatur abgeschlossen.")
        with st.expander("Vorschau (erster Teil)"):
            st.markdown(repaired[:10000])
        st.download_button("Reparierte Markdown herunterladen", repaired.encode("utf-8"), file_name="repaired.md")

# Merge Tab: Markdown-Dateien zusammenführen
with tab_merge:
    st.subheader("Markdown zusammenführen")
    st.caption("Wähle mehrere .md/.markdown/.txt – wir erzeugen eine kombinierte Datei. Optional: Frontmatter entfernen, Dateinamen als Abschnittsüberschriften und ein Inhaltsverzeichnis.")

    merge_files = st.file_uploader("Markdown-Dateien auswählen", type=["md", "markdown", "txt"], accept_multiple_files=True)
    colA, colB, colC = st.columns([1,1,1])
    with colA:
        use_headings = st.checkbox("Dateiname als H2-Überschrift", value=True)
    with colB:
        add_toc = st.checkbox("TOC erzeugen", value=True)
    with colC:
        drop_frontmatter = st.checkbox("Frontmatter entfernen", value=True)
    sep = st.text_input("Trenner zwischen Dateien", value="\n\n---\n\n")
    merge_output_name = st.text_input("Ausgabename (ohne .md)", value="")

    if merge_files and st.button("Zusammenführen"):
        parts = []
        toc = ["## Inhalt"] if add_toc else []
        for idx, mf in enumerate(sorted(merge_files, key=lambda x: x.name.lower()), start=1):
            try:
                text = mf.read().decode("utf-8", errors="ignore")
            except Exception:
                text = mf.getvalue().decode("utf-8", errors="ignore")
            if drop_frontmatter:
                text = strip_frontmatter(text)
            heading = os.path.splitext(os.path.basename(mf.name))[0]
            anchor = re.sub(r"[^a-z0-9\-]+", "-", heading.lower()).strip("-")
            if use_headings:
                parts.append(f"\n\n<a name=\"{anchor}\"></a>\n## {heading}\n\n")
            if add_toc:
                toc.append(f"- [{heading}](#{anchor})")
            parts.append(text.strip())
            if idx != len(merge_files) and sep:
                parts.append(sep)

        merged = ("\n\n".join(toc) + "\n\n" if toc else "") + "\n".join(parts)

        # Optional Post-Processing (sanfte Normalisierung nur):
        merged = re.sub(r"\n{3,}", "\n\n", merged)

        # Speichern & Download anbieten
        out_slug = f"merge-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        out_dir = os.path.join(OUT_DIR, out_slug)
        os.makedirs(out_dir, exist_ok=True)
        file_base = merge_output_name.strip() or out_slug
        out_md = os.path.join(out_dir, f"{file_base}.md")
        with open(out_md, "w", encoding="utf-8") as oh:
            oh.write(merged)

        st.success(f"Fertig: {out_md}")
        with st.expander("Vorschau (erster Teil)"):
            st.markdown(merged[:10000])
        st.download_button("Kombiniertes Markdown herunterladen", merged.encode("utf-8"), file_name=f"{file_base}.md")

        log_job({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "source": ", ".join([mf.name for mf in merge_files]),
            "engine": "merge-md",
            "ocr": "",
            "duration_ms": "",
            "output_path": out_md,
            "status": "ok",
            "error": ""
        })


with tab_joblog:
    st.subheader("Job-Log")
    rows = read_joblog_all()
    if not rows:
        st.caption("Noch keine Jobs protokolliert.")
    else:
        import pandas as pd
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        cols = list(df.columns)
        csv_rows = [",".join(cols)]
        for r in rows:
            csv_rows.append(
                ",".join(str(r.get(c, "")).replace(",", " ") for c in cols)
            )
        st.download_button("CSV herunterladen", data="\n".join(csv_rows), file_name="joblog.csv", mime="text/csv")

def list_new_files(seen: set[str]) -> list[str]:
    os.makedirs(IN_DIR, exist_ok=True)
    files = []
    for name in os.listdir(IN_DIR):
        p = os.path.join(IN_DIR, name)
        if os.path.isfile(p) and p not in seen:
            files.append(p)
    return files

if "seen_files" not in st.session_state:
    st.session_state.seen_files = set()

with tab_watch:
    if enable_watcher:
        st.write("👀 Watcher aktiv…")
        new_files = list_new_files(st.session_state.seen_files)
        if new_files:
            st.write(f"Neue Dateien: {', '.join(os.path.basename(n) for n in new_files)}")
            # Simuliere Upload-Flow
            class _F: pass
            uploaded = []
            for p in new_files:
                f = _F()
                f.name = os.path.basename(p)
                with open(p, "rb") as fh:
                    f.data = fh.read()
                uploaded.append(f)
            # Re-use Konvertierungslogik
            for f in uploaded:
                input_path = os.path.join(IN_DIR, f.name)
                # (Datei liegt ja schon da)
                slug = slugify(f.name)
                base_name = output_name.strip() or slug
                target_dir = os.path.join(OUT_DIR, slug)
                assets_dir = os.path.join(target_dir, "assets")
                os.makedirs(target_dir, exist_ok=True)
                os.makedirs(assets_dir, exist_ok=True)

                pick = choose_engine(input_path, engine)
                _t0 = time.time()
                with st.status(f"[Watcher] Konvertiere **{f.name}** …", expanded=False) as status:
                    try:
                        if pick == "MarkItDown":
                            md_text = convert_markitdown(input_path)
                        elif pick == "Docling":
                            md_text = convert_docling(input_path)
                        elif pick == "pptx2md":
                            md_text = convert_pptx2md(input_path, target_dir)
                        elif pick == "plain":
                            md_text = convert_plain_text(input_path)
                        else:
                            is_pdf = input_path.lower().endswith(".pdf")
                            use_chunk = False
                            if is_pdf:
                                pc = get_pdf_page_count(input_path)
                                if pc != -1 and pc > int(AUTO_CHUNK_THRESHOLD):
                                    use_chunk = True
                                    st.caption(f"[Watcher] Auto-Chunk aktiv: {pc} Seiten > {int(AUTO_CHUNK_THRESHOLD)} → Chunk-Größe {int(chunk_size)}.")
                            if is_pdf and use_chunk:
                                md_text, marker_logs = convert_marker_chunked(
                                    input_path, target_dir, force_ocr, keep_images, int(chunk_size),
                                    live_cb=None,
                                    cleanup=cleanup_chunks
                                )
                            else:
                                md_text, marker_logs = convert_marker_cli(input_path, target_dir, force_ocr, keep_images, live_cb=None)

                        md_text = postprocess_markdown(md_text, assets_rel="./assets")

                        if add_frontmatter:
                            tags = [t.strip() for t in tags_default.split(",") if t.strip()]
                            md_text = write_frontmatter(md_text, title=slug, src_name=f.name, tags=tags)

                        out_md = os.path.join(target_dir, f"{base_name}.md")
                        with open(out_md, "w", encoding="utf-8") as oh:
                            oh.write(md_text)

                        dur_ms = int((time.time() - _t0) * 1000)
                        if pick == "Marker":
                            with st.expander(f"[Watcher] Marker-Logs für {f.name}"):
                                st.code(marker_logs or "(keine Logs)", language="bash")
                            with st.expander(f"[Watcher] Asset-Kopierbericht für {f.name}"):
                                asset_lines = "\n".join([ln for ln in (marker_logs or "").splitlines() if ln.startswith("[assets]")])
                                st.code(asset_lines or "(keine Assets gefunden oder kopiert)", language="bash")    
                        st.success(f"[Watcher] Fertig: {out_md} · {dur_ms} ms")
                        if delete_after_success:
                            try:
                                delete_from_inbox(input_path)
                                st.caption(f"[Watcher] Quelle gelöscht: {input_path}")
                            except Exception:
                                st.caption(f"[Watcher] Quelle konnte nicht gelöscht werden: {input_path}")
                        log_job({
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "source": f.name,
                            "engine": pick,
                            "ocr": ocr_engine if pick == "Docling" else "",
                            "duration_ms": dur_ms,
                            "output_path": out_md,
                            "status": "ok",
                            "error": ""
                        })
                        st.session_state.seen_files.add(input_path)
                        status.update(label="[Watcher] Konvertierung abgeschlossen", state="complete")
                    except Exception as e:
                        dur_ms = int((time.time() - _t0) * 1000)
                        st.error(f"[Watcher] Fehler bei {f.name}: {e}")
                        st.info("Tipp: Siehe Empfehlungen oben. Passe ggf. OCR, Chunk-Größe oder Engine an und starte erneut.")
                        with st.expander(f"[Watcher] Fehlerdetails / Logs für {f.name}"):
                            st.code(str(e), language="bash")
                        log_job({
                            "timestamp": datetime.now().isoformat(timespec="seconds"),
                            "source": f.name,
                            "engine": pick,
                            "ocr": ocr_engine if pick == "Docling" else "",
                            "duration_ms": dur_ms,
                            "output_path": "",
                            "status": "error",
                            "error": str(e)
                        })
                        status.update(label="[Watcher] Fehlgeschlagen", state="error")

        # Auto-Refresh
        time.sleep(watch_interval)
        st.rerun()