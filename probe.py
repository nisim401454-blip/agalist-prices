"""Proof step for agalist-prices: download a small sample of the public price files
and write a short report describing what arrived (file names, sizes, XML structure)."""
import json, os, sys, traceback
import xml.etree.ElementTree as ET
from il_supermarket_scarper import ScarpingTask

CHAINS = ["SHUFERSAL", "RAMI_LEVY", "OSHER_AD", "YOHANANOF", "TIV_TAAM", "YELLOW"]
report = {"chains": {}, "errors": []}


def run(files_types, limit):
    try:
        task = ScarpingTask(enabled_scrapers=CHAINS, files_types=files_types, multiprocessing=3)
        task.start(limit=limit)
        task.join()
    except Exception:  # keep going: the report says what failed
        report["errors"].append(traceback.format_exc()[-1500:])


def strip(tag):
    return tag.split("}")[-1]


def describe(path):
    info = {"file": os.path.basename(path), "bytes": os.path.getsize(path)}
    try:
        root = ET.parse(path).getroot()
        info["root"] = strip(root.tag)
        info["top"] = {strip(c.tag): (c.text or "").strip()[:60] for c in list(root)[:25] if len(c) == 0}
        best = None
        for el in root.iter():
            kids = list(el)
            if len(kids) > 3 and kids[0].tag == kids[1].tag and len(kids[0]) > 2:
                if best is None or len(kids) > len(list(best)):
                    best = el
        if best is not None:
            kids = list(best)
            info["records_tag"] = strip(kids[0].tag)
            info["records"] = len(kids)
            info["samples"] = [{strip(f.tag): (f.text or "").strip()[:80] for f in k if len(f) == 0} for k in kids[:3]]
    except Exception as error:
        info["parse_error"] = str(error)[:300]
    return info


run(["STORE_FILE"], None)
run(["PRICE_FULL_FILE"], 2)

for base, _dirs, files in os.walk("dumps"):
    for name in sorted(files):
        if not name.lower().endswith(".xml"):
            continue
        chain = os.path.relpath(base, "dumps").split(os.sep)[0]
        report["chains"].setdefault(chain, []).append(describe(os.path.join(base, name)))

os.makedirs("proof", exist_ok=True)
with open("proof/report.json", "w", encoding="utf8") as out:
    json.dump(report, out, ensure_ascii=False, indent=1)
for chain, files in report["chains"].items():
    print(chain, [(f["file"], f["bytes"], f.get("records")) for f in files])
print("errors:", len(report["errors"]))
