import re, json, os
from datetime import datetime
from typing import Tuple, List, Dict, Any

# -------- Frontmatter helpers --------

def _split_frontmatter(md: str) -> Tuple[str, str]:
    s = md.lstrip()
    if not s.startswith('---'):
        return "", md
    lines = md.splitlines()
    if len(lines) < 3:
        return "", md
    if lines[0].strip() != '---':
        # leading whitespace case
        start = next((i for i, ln in enumerate(lines) if ln.strip() == '---'), None)
        if start is None:
            return "", md
        # search closing
        end = None
        for j in range(start+1, len(lines)):
            if lines[j].strip() == '---':
                end = j
                break
        if end is None:
            return "", md
        return "\n".join(lines[start:end+1]) + "\n", "\n".join(lines[end+1:]) + ("\n" if md.endswith("\n") else "")
    # normal case (no leading spaces)
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            end = i
            break
    if end is None:
        return "", md
    return "\n".join(lines[:end+1]) + "\n", "\n".join(lines[end+1:]) + ("\n" if md.endswith("\n") else "")

def _parse_json_frontmatter(front: str) -> Dict[str, Any]:
    if not front:
        return {}
    inner = front.strip()
    if inner.startswith("---"):
        inner = inner.strip("-").strip()
    try:
        return json.loads(inner)
    except Exception:
        # not JSON → return empty; the caller will append YAML-like tags as best effort
        return {}

def _compose_json_frontmatter(data: Dict[str, Any]) -> str:
    return f"---\n{json.dumps(data, ensure_ascii=False, indent=2)}\n---\n"

# -------- Text block helpers (protect code blocks) --------

_FENCE_RE = re.compile(r"^```.*$")

def _split_code_blocks(text: str) -> List[Tuple[bool, str]]:
    """Split into [(is_code, chunk), ...] preserving order."""
    parts: List[Tuple[bool, str]] = []
    buf: List[str] = []
    in_code = False
    for ln in text.splitlines():
        if _FENCE_RE.match(ln.strip()):
            # push current buffer
            if buf:
                parts.append((in_code, "\n".join(buf) + "\n"))
                buf = []
            # toggle state including the fence line itself
            parts.append((True, ln + "\n"))
            in_code = not in_code
        else:
            buf.append(ln)
    if buf:
        parts.append((in_code, "\n".join(buf) + ("\n" if text.endswith("\n") else "")))
    return parts

def _join_code_blocks(parts: List[Tuple[bool, str]]) -> str:
    return "".join(chunk for _is_code, chunk in parts)

# -------- Repairs --------

def _normalize_headings(text: str) -> str:
    """Ensure H levels don't jump more than +1; keep at least one leading '#'.
    Only handle lines starting with '#'.
    """
    out = []
    last_level = None
    for ln in text.splitlines():
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if not m:
            out.append(ln)
            continue
        hashes, title = m.group(1), m.group(2)
        lvl = len(hashes)
        if last_level is None:
            last_level = lvl
        # Avoid upward jumps larger than 1
        if last_level is not None and lvl > last_level + 1:
            lvl = last_level + 1
        # Avoid lvl==0 (not possible) and cap at 6
        lvl = max(1, min(6, lvl))
        out.append("#" * lvl + " " + title.strip())
        last_level = lvl
    return "\n".join(out)

def _fix_lists(text: str) -> str:
    """Normalize bullet markers to '-', ensure single space after marker, 2-space indents for nesting."""
    out = []
    for ln in text.splitlines():
        m = re.match(r"^(\s*)([-*+]|[0-9]+\.)\s+(.*)$", ln)
        if not m:
            out.append(ln)
            continue
        indent, marker, rest = m.groups()
        # keep ordered lists as "1." but normalize spacing; unordered to "-"
        if re.match(r"^[0-9]+\.$", marker):
            new_marker = marker  # keep numbering
        else:
            new_marker = "-"
        # normalize indent to multiples of 2 spaces
        ind_len = len(indent.replace("\t", "  "))
        new_indent = " " * (2 * (ind_len // 2))
        out.append(f"{new_indent}{new_marker} {rest.strip()}")
    return "\n".join(out)

def _close_unbalanced_code_fences(text: str) -> str:
    """If the number of ``` fences is odd, append one closing fence at end."""
    fence_count = len(re.findall(r"^```", text, flags=re.MULTILINE))
    if fence_count % 2 != 0:
        return text.rstrip() + "\n```\n"
    return text

def _fix_german_quotes(text: str) -> str:
    """Replace straight quotes with „…“ on non-code lines without backticks; conservative regex."""
    out = []
    for ln in text.splitlines():
        if "`" in ln:  # skip inline/code
            out.append(ln)
            continue
        # replace "word or phrase" with „word or phrase“
        def repl(m):
            inner = m.group(1)
            return f"„{inner}“"
        ln2 = re.sub(r"\"([^\"]{1,80})\"", repl, ln)
        out.append(ln2)
    return "\n".join(out)

def _regenerate_toc_if_marked(text: str) -> str:
    """Regenerate TOC only if markers are present: <!-- TOC --> ... <!-- /TOC -->."""
    start = text.find("<!-- TOC -->")
    end = text.find("<!-- /TOC -->")
    if start == -1 or end == -1 or end <= start:
        return text

    body_before = text[:start]
    body_after = text[end + len("<!-- /TOC -->"):]
    main = text[start:end]

    # collect headings from body_after (whole doc) — simple slugify
    def _slug(s: str) -> str:
        s = s.strip().lower()
        s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
        s = re.sub(r"\s+", "-", s)
        return s

    headings = re.findall(r"^(#{1,6})\s+(.*)$", body_after, flags=re.MULTILINE)
    items = []
    for hashes, title in headings:
        level = len(hashes)
        anchor = _slug(title)
        indent = "  " * (level - 1)
        items.append(f"{indent}- [{title}](#{anchor})")

    toc_md = "\n".join(items) + "\n"
    return body_before + "<!-- TOC -->\n" + toc_md + "<!-- /TOC -->" + body_after

def _validate_asset_links(text: str, assets_dir: str = "") -> str:
    """Append an HTML comment report about asset link validity.
    If assets_dir exists, we check file existence for ./assets/<name>.
    """
    links = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)
    report = ["validation: assets"]
    ok = 0
    missing = 0
    unknown = 0
    for href in links:
        if href.startswith(("http://", "https://", "data:", "#")):
            continue
        # normalize
        href_norm = href
        if href_norm.startswith("./"):
            href_norm = href_norm[2:]
        if href_norm.startswith("assets/"):
            if assets_dir and os.path.isdir(assets_dir):
                p = os.path.join(assets_dir, os.path.basename(href_norm))
                if os.path.exists(p):
                    ok += 1
                    report.append(f"OK {href}")
                else:
                    missing += 1
                    report.append(f"MISSING {href}")
            else:
                unknown += 1
                report.append(f"UNKNOWN {href} (assets_dir not provided)")
    report.append(f"SUMMARY ok={ok} missing={missing} unknown={unknown}")
    return text.rstrip() + "\n\n<!-- " + " | ".join(report) + " -->\n"

def _ensure_frontmatter_template(data: Dict[str, Any], extra_tags: List[str]) -> Dict[str, Any]:
    # base fields
    defaults = {
        "title": data.get("title", ""),
        "source_file": data.get("source_file", ""),
        "imported_at": data.get("imported_at", datetime.now().isoformat(timespec="seconds")),
        "tags": sorted(set((data.get("tags") or []) + (extra_tags or []))),
        # suggested additional fields
        "author": data.get("author", ""),
        "course": data.get("course", ""),
        "semester": data.get("semester", ""),
        "topic": data.get("topic", ""),
        # optional helper to allow validation:
        # if you set this to your folder path, link validation will check real files
        "assets_dir": data.get("assets_dir", ""),
    }
    return defaults

# -------- Public API --------

def load_markdown_and_repair(
    md_text: str,
    extra_tags: list[str],
    *,
    apply_quotes: bool = True,
    regen_toc: bool = True,
    fm_overrides: Dict[str, Any] | None = None,
    assets_dir: str | None = None,
) -> str:
    # 1) Frontmatter split & parse
    fm_text, body = _split_frontmatter(md_text)
    data = _parse_json_frontmatter(fm_text)
    data = _ensure_frontmatter_template(data, extra_tags or [])

    # Apply frontmatter overrides and explicit assets_dir from UI
    if fm_overrides:
        for k in ("author", "course", "semester", "topic", "title"):
            if k in fm_overrides and fm_overrides[k] is not None:
                data[k] = fm_overrides[k]
    if assets_dir:
        data["assets_dir"] = assets_dir

    # 2) Work on non-code parts for risky transforms (headings, lists, quotes)
    parts = _split_code_blocks(body)

    repaired_parts: List[Tuple[bool, str]] = []
    for is_code, chunk in parts:
        if is_code:
            repaired_parts.append((True, chunk))
            continue
        # operations on prose
        chunk = _normalize_headings(chunk)
        chunk = _fix_lists(chunk)
        if apply_quotes:
            chunk = _fix_german_quotes(chunk)
        repaired_parts.append((False, chunk))

    body_repaired = _join_code_blocks(repaired_parts)

    # 3) Ensure code fences balanced
    body_repaired = _close_unbalanced_code_fences(body_repaired)

    # 4) Optional TOC regeneration if markers are present
    if regen_toc:
        body_repaired = _regenerate_toc_if_marked(body_repaired)

    # 5) Compose frontmatter
    fm_text = _compose_json_frontmatter(data)

    # 6) Validate asset links (only if assets_dir provided)
    assets_for_validate = assets_dir or data.get("assets_dir") or ""
    body_repaired = _validate_asset_links(body_repaired, assets_dir=assets_for_validate)

    # 7) Return combined
    return fm_text + "\n" + body_repaired.lstrip("\n")