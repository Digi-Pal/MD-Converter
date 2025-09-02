# repair_merge_once.py
import os, re, shutil, sys

base = sys.argv[1]  # z.B. ./data/out/hr_folien_ws_2021-1
final_md = os.path.join(base, "hr_folien_ws_2021-1.md")
assets = os.path.join(base, "assets")
os.makedirs(assets, exist_ok=True)

# 1) Assets einsammeln & präfixen
chunks = sorted([d for d in os.listdir(base) if d.startswith("_chunk_")])
for i, d in enumerate(chunks, start=1):
    prefix = f"c{i:02d}_"
    co = os.path.join(base, d)
    cand = os.path.join(co, "assets") if os.path.isdir(os.path.join(co,"assets")) else co
    for name in os.listdir(cand):
        src = os.path.join(cand, name)
        if os.path.isfile(src) and re.search(r"\.(png|jpg|jpeg|webp|gif|svg)$", name, re.I):
            shutil.copy2(src, os.path.join(assets, prefix + name))

# 2) Links in der finalen MD umschreiben
with open(final_md, "r", encoding="utf-8") as f:
    md = f.read()

def rewr(m):
    alt, href = m.group(1), m.group(2)
    if href.startswith(("http://","https://","data:", "#")):
        return m.group(0)
    fname = os.path.basename(href)
    # versuche, Prefix anhand Chunknummer zu schätzen: _chunk_XX im Kontext
    # (Fallback: kein Mapping → belasse fname, damit wenigstens Assets da sind)
    return f"![{alt}](./assets/{fname})"

md = re.sub(r'!\[(.*?)\]\(([^)\s]+)\)', rewr, md)

with open(final_md, "w", encoding="utf-8") as f:
    f.write(md)

print("Reparatur abgeschlossen:", final_md)