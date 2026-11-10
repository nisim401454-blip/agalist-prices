"""Downloads one chain's public store list and full price files, and writes a compact
per-chain file: a base price list per sub-chain plus per-store differences."""
import collections, datetime, gzip, json, os, re, sys, traceback
import xml.etree.ElementTree as ET

from il_supermarket_scarper import ScarpingTask
from il_supermarket_scarper.utils import _now

CHAIN = sys.argv[1]
CONFIG = json.load(open("config.json", encoding="utf8"))
LIMIT = CONFIG.get("limit") or None
log = {"chain": CHAIN, "errors": [], "price_files": 0, "store_files": 0}


def scrape(types, when=None, limit=None):
    if os.environ.get("AGALIST_NO_SCRAPE"):
        return
    try:
        task = ScarpingTask(enabled_scrapers=[CHAIN], files_types=types, multiprocessing=4)
        task.start(limit=limit, when_date=when)
        task.join()
    except Exception:
        log["errors"].append(traceback.format_exc()[-1200:])


def xml_files(prefix):
    found = []
    for base, _dirs, files in os.walk("dumps"):
        for name in files:
            if name.lower().endswith(".xml") and name.lower().startswith(prefix):
                found.append(os.path.join(base, name))
    return sorted(found)


def tag(el):
    return el.tag.split("}")[-1].lower()


def norm_id(value):
    value = (value or "").strip()
    return value.lstrip("0") or "0"


def text(fields, *names):
    for name in names:
        value = fields.get(name)
        if value and value.strip() and value.strip().lower() not in ("unknown", "לא ידוע"):
            return value.strip()
    return ""


def parse_stores(path, stores, meta):
    root = ET.parse(path).getroot()

    def walk(el, sub):
        for child in el:
            name = tag(child)
            if len(child) == 0:
                if name == "chainid" and child.text:
                    meta["chain_id"] = child.text.strip()
                if name == "chainname" and child.text:
                    meta["chain_name"] = child.text.strip()
                continue
            if name == "store":
                fields = {tag(f): (f.text or "") for f in child if len(f) == 0}
                if not fields.get("storeid"):
                    continue
                if fields.get("chainname", "").strip():
                    meta.setdefault("chain_name", fields["chainname"].strip())
                if fields.get("storetype", "").strip() == "2":
                    continue  # online-only store
                stores[norm_id(fields["storeid"])] = {
                    "sub": norm_id(fields.get("subchainid") or sub),
                    "subname": text(fields, "subchainname"),
                    "name": text(fields, "storename"),
                    "addr": text(fields, "address"),
                    "city": text(fields, "city"),
                    "zip": text(fields, "zipcode"),
                }
                continue
            next_sub = sub
            if name == "subchain":
                for f in child:
                    if tag(f) == "subchainid" and f.text:
                        next_sub = f.text.strip()
            walk(child, next_sub)

    walk(root, "0")


def parse_prices(path):
    header, items = {}, {}
    for _event, el in ET.iterparse(path, events=("end",)):
        name = tag(el)
        if name in ("chainid", "subchainid", "storeid") and name not in header and el.text:
            header[name] = el.text.strip()
        elif name in ("item", "product") and len(el):
            fields = {tag(f): (f.text or "") for f in el}
            code = fields.get("itemcode", "").strip()
            try:
                price = round(float(fields.get("itemprice", "0") or 0), 2)
            except ValueError:
                price = 0
            if code and price > 0:
                weighted = 1 if fields.get("bisweighted", "").strip() == "1" else 0
                barcode = code.isdigit() and len(code) >= 8
                if barcode or weighted:
                    items[code] = (
                        price,
                        text(fields, "itemname", "itemnm"),
                        text(fields, "manufacturername", "manufacturename"),
                        text(fields, "quantity"),
                        text(fields, "unitqty", "unitofmeasure"),
                        weighted,
                    )
            el.clear()
    return header, items


def main():
    scrape(["STORE_FILE"])
    today = _now()
    scrape(["PRICE_FULL_FILE"], when=today, limit=LIMIT)
    if not xml_files("pricefull"):
        scrape(["PRICE_FULL_FILE"], when=today - datetime.timedelta(days=1), limit=LIMIT)

    stores, meta = {}, {}
    for path in xml_files("store"):
        try:
            parse_stores(path, stores, meta)
            log["store_files"] += 1
        except Exception as error:
            log["errors"].append(f"{os.path.basename(path)}: {error}"[:300])

    latest = {}  # store id -> (file name, path): the newest price file wins
    names = {}
    prices, subs, catalog = {}, {}, {}
    for path in xml_files("pricefull"):
        try:
            header, items = parse_prices(path)
        except Exception as error:
            log["errors"].append(f"{os.path.basename(path)}: {error}"[:300])
            continue
        if not items or "storeid" not in header:
            continue
        sid = norm_id(header["storeid"])
        stamp = re.sub(r"\D", "", os.path.basename(path))[-14:]
        if sid in latest and latest[sid] >= stamp:
            continue
        latest[sid] = stamp
        log["price_files"] += 1
        meta.setdefault("chain_id", header.get("chainid", ""))
        subs[sid] = norm_id(header.get("subchainid", "0"))
        prices[sid] = {code: row[0] for code, row in items.items()}
        for code, row in items.items():
            if code not in catalog or (row[1] and not catalog[code][0]):
                catalog[code] = [row[1], row[2], row[3], row[4], row[5]]

    # base list per sub-chain: the most common price of every item sold by at least half of its stores
    by_sub = collections.defaultdict(list)
    for sid in prices:
        by_sub[subs[sid]].append(sid)
    base, diff = {}, {}
    for sub, sids in by_sub.items():
        counts = collections.defaultdict(collections.Counter)
        for sid in sids:
            for code, price in prices[sid].items():
                counts[code][price] += 1
        base[sub] = {
            code: counter.most_common(1)[0][0]
            for code, counter in counts.items()
            if sum(counter.values()) * 2 >= len(sids)
        }
        for sid in sids:
            mine, common, delta = prices[sid], base[sub], {}
            for code, price in mine.items():
                if common.get(code) != price:
                    delta[code] = price
            for code in common:
                if code not in mine:
                    delta[code] = 0
            diff[sid] = delta

    out = {
        "chain": CHAIN,
        "chain_id": meta.get("chain_id", ""),
        "chain_name": meta.get("chain_name", ""),
        "date": _now().strftime("%Y-%m-%d"),
        "stores": {sid: dict(stores.get(sid, {}), sub=subs[sid]) for sid in prices},
        "all_stores": len(stores),
        "items": catalog,
        "base": base,
        "diff": diff,
        "log": log,
    }
    os.makedirs("out", exist_ok=True)
    if prices:
        with gzip.open(f"out/{CHAIN}.json.gz", "wt", encoding="utf8") as handle:
            json.dump(out, handle, ensure_ascii=False, separators=(",", ":"))
    with open(f"out/{CHAIN}.log.json", "w", encoding="utf8") as handle:
        json.dump(dict(log, stores=len(stores), priced_stores=len(prices), items=len(catalog)), handle, ensure_ascii=False)
    print(json.dumps(dict(log, stores=len(stores), priced_stores=len(prices), items=len(catalog)), ensure_ascii=False)[:2000])


main()
