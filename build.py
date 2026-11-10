"""Merges the per-chain files into the small public files the Agalist app reads:
products.json, cities.json, chains.json, city/<code>.json and status.json."""
import collections, gzip, io, json, math, os, re, shutil, time, urllib.parse, urllib.request, zlib

CONFIG = json.load(open("config.json", encoding="utf8"))
GENERICS = json.load(open("generics.json", encoding="utf8"))
BASE_URL = CONFIG["base_url"]
UA = {"User-Agent": "agalist-prices/1.0 (+https://github.com/nisim401454-blip/agalist-prices)"}
STATUS = {"built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "chains": {}, "notes": []}
QUOTES = str.maketrans("", "", "\"'`׳״’")


def http(url, timeout=40):
    if os.environ.get("AGALIST_OFFLINE"):
        raise OSError("offline test")
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def previous(path, default):
    try:
        return json.loads(http(BASE_URL + path))
    except Exception as error:
        STATUS["notes"].append(f"no previous {path}: {str(error)[:80]}")
        return default


def clean(value):
    return re.sub(r"\s+", " ", (value or "").translate(QUOTES)).strip().lower()


def number(value):
    try:
        number_ = float(value)
        return str(int(number_)) if number_ == int(number_) else str(round(number_, 2))
    except (TypeError, ValueError):
        return ""


# ---------- 1. chain files: tonight's download, or the last published one ----------
chains = {}
for name in CONFIG["chains"]:
    path = f"art/{name}.json.gz"
    data, source = None, "new"
    if os.path.exists(path):
        data = json.load(gzip.open(path, "rt", encoding="utf8"))
    else:
        source = "previous"
        try:
            raw = http(BASE_URL + f"chains/{name}.json.gz", timeout=120)
            data = json.loads(gzip.decompress(raw).decode("utf8"))
        except Exception:
            data = None
    log_path = f"art/{name}.log.json"
    log = json.load(open(log_path, encoding="utf8")) if os.path.exists(log_path) else {}
    STATUS["chains"][name] = {
        "source": source if data else "missing",
        "date": data.get("date") if data else None,
        "stores": len(data["stores"]) if data else 0,
        "listed_stores": (data or {}).get("all_stores", 0),
        "items": len(data["items"]) if data else 0,
        "errors": log.get("errors", [])[:3],
    }
    if data and data["stores"]:
        chains[name] = data
print("chains loaded:", {k: v["stores"] for k, v in STATUS["chains"].items()})

# ---------- 2. localities (official code -> Hebrew name) ----------
localities = {}
try:
    url = "https://data.gov.il/api/3/action/datastore_search?resource_id=5c78e9fa-c2e2-4771-93ff-7f400a12f7ba&limit=3000"
    for row in json.loads(http(url))["result"]["records"]:
        code = str(row.get("סמל_ישוב", "")).strip().lstrip("0")
        name = re.sub(r"\s+", " ", str(row.get("שם_ישוב", ""))).strip()
        if code and name:
            localities[code] = name
    STATUS["localities"] = "data.gov.il"
except Exception as error:
    STATUS["notes"].append(f"data.gov.il failed: {str(error)[:120]}")
if len(localities) < 500:
    localities = previous("localities.json", {}) or localities
    STATUS["localities"] = "previous"
if os.path.exists("localities_seed.json"):
    for code, name in json.load(open("localities_seed.json", encoding="utf8")).items():
        localities.setdefault(code, name)
name_to_code = {clean(name).replace("-", " "): code for code, name in localities.items()}
STATUS["localities_count"] = len(localities)


def resolve_city(raw):
    raw = (raw or "").strip()
    if raw.isdigit():
        code = raw.lstrip("0")
        if code and code in localities:
            return code, localities[code]
        return ("", "") if not code else (code, "")
    key = clean(raw).replace("-", " ")
    if not key:
        return "", ""
    if key in name_to_code:
        return name_to_code[key], localities[name_to_code[key]]
    return "x%08x" % zlib.crc32(key.encode("utf8")), raw


# ---------- 3. product universe ----------
chain_count = collections.Counter()
store_count = collections.Counter()
for name, data in chains.items():
    subs = collections.defaultdict(list)
    for sid, store in data["stores"].items():
        subs[store["sub"]].append(sid)
    seen = set()
    for sub, sids in subs.items():
        base = data["base"].get(sub, {})
        absent = collections.Counter()
        for sid in sids:
            for code, price in data["diff"].get(sid, {}).items():
                if code in base:
                    if price == 0:
                        absent[code] += 1
                elif price > 0:
                    store_count[(name, code)] += 1
                    seen.add(code)
        for code in base:
            store_count[(name, code)] += len(sids) - absent[code]
            seen.add(code)
    for code in seen:
        if code.isdigit() and len(code) >= 8:
            chain_count[code] += 1

total_stores = collections.Counter()
for (name, code), count in store_count.items():
    total_stores[code] += count
universe = [code for code, count in chain_count.items() if count >= CONFIG.get("min_chains", 2)]
universe.sort(key=lambda code: -total_stores[code])
universe = universe[: CONFIG.get("max_products", 30000)]


def describe(code):
    for name in CONFIG["chains"]:
        row = chains.get(name, {}).get("items", {}).get(code)
        if row and row[0]:
            qty = number(row[2])
            unit = row[3]
            size = f"{qty} {unit}".strip() if qty and qty != "0" else ""
            return row[0], row[1], size
    return "", "", ""


# ---------- 4. loose items matched by name, per chain ----------
generic_codes = {}  # chain -> generic index -> codes ordered by how many stores carry them
for name, data in chains.items():
    per_chain = {}
    weighted = [(code, clean(row[0])) for code, row in data["items"].items() if row[4] == 1 and row[0]]
    for index, generic in enumerate(GENERICS):
        wanted = [clean(term) for term in generic["any"]]
        banned = [clean(term) for term in generic["not"]]
        matches = [
            code
            for code, label in weighted
            if any(term in label for term in wanted) and not any(term in label for term in banned)
        ]
        matches.sort(key=lambda code: (-store_count[(name, code)], len(data["items"][code][0])))
        if matches:
            per_chain[index] = matches[:6]
    generic_codes[name] = per_chain

products = []
for index, generic in enumerate(GENERICS):
    products.append(["g:" + generic["id"], generic["name"], "", "ק\"ג", 0, 0, generic["any"], generic["not"]])
offset = len(products)
index_of = {}
for code in universe:
    label, maker, size = describe(code)
    if not label:
        continue
    index_of[code] = len(products)
    products.append([code, label, maker, size, total_stores[code], chain_count[code]])
STATUS["products"] = len(products)

# ---------- 5. store locations ----------
geo = previous("geo.json", {})
budget = CONFIG.get("geocode_budget", 4000)
used = 0


def in_israel(lat, lon):
    return 29.3 <= lat <= 33.45 and 34.2 <= lon <= 35.95


def nominatim(query, details=False):
    global used
    if used >= budget:
        return None
    used += 1
    if os.environ.get("AGALIST_FAKE_GEO"):
        seed = zlib.crc32(query.encode("utf8"))
        if details:
            return [32.05, 34.8, "ירושלים"]
        return [round(32.0 + (seed % 1000) / 2000, 5), round(34.8 + ((seed >> 10) % 1000) / 4000, 5)]
    time.sleep(1.1)
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "countrycodes": "il", "accept-language": "he", "addressdetails": 1}
    )
    try:
        rows = json.loads(http(url, timeout=25))
        if rows:
            lat, lon = round(float(rows[0]["lat"]), 5), round(float(rows[0]["lon"]), 5)
            if in_israel(lat, lon):
                if details:
                    address = rows[0].get("address", {})
                    place = address.get("city") or address.get("town") or address.get("village") or address.get("municipality") or ""
                    return [lat, lon, place]
                return [lat, lon]
    except Exception as error:
        if len(STATUS["notes"]) < 30:
            STATUS["notes"].append(f"geocode error: {str(error)[:80]}")
    return None


def city_center(code, name):
    key = "city|" + code
    if key not in geo and name:
        geo[key] = nominatim(name + ", ישראל") or (None if used >= budget else [])
        if geo[key] is None:
            del geo[key]
    return geo.get(key) or None


def locate(key, store, code, city_name):
    hit = geo.get(key) or None
    address = re.sub(r"[,;]+", " ", store.get("addr", "")).strip()
    if hit and hit[3:4] == [address]:
        return hit[:3]
    center = city_center(code, city_name)
    point = None
    if address and city_name and len(address) > 3:
        point = nominatim(f"{address}, {city_name}")
        if point and center and distance(point, center) > 25:
            point = None
    if point:
        geo[key] = point + [0, address]
        return geo[key][:3]
    if center:
        seed = zlib.crc32(key.encode("utf8"))
        jitter = [((seed & 0xFF) - 128) / 128 * 0.006, (((seed >> 8) & 0xFF) - 128) / 128 * 0.006]
        approx = [round(center[0] + jitter[0], 5), round(center[1] + jitter[1], 5), 1]
        if used < budget:
            geo[key] = approx + [address]
        return approx
    return None


def guess_city(key, chain, store):
    """For stores published without a city: find the branch by name, then read the city from the map."""
    hit = geo.get(key)
    if hit and len(hit) >= 5:
        return hit[4], localities.get(hit[4], ""), hit[:3]
    if hit == []:
        return "", "", None
    label = CONFIG["names"].get(chain, "")
    found = None
    for query in (f"{label} {store.get('name', '')}".strip(), store.get("addr", "")):
        if len(query) > 5:
            found = nominatim(query, details=True)
            if found and name_to_code.get(clean(found[2]).replace("-", " ")):
                break
            found = None
    if not found:
        if used < budget:
            geo[key] = []
        return "", "", None
    code = name_to_code[clean(found[2]).replace("-", " ")]
    geo[key] = [found[0], found[1], 1, store.get("addr", ""), code]
    return code, localities[code], geo[key][:3]


def distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


# ---------- 6. city files ----------
cities = collections.defaultdict(lambda: {"stores": [], "bases": {}})
skipped = collections.Counter()
for name, data in chains.items():
    base_index = {}
    for sub, base in data["base"].items():
        base_index[sub] = {index_of[code]: price for code, price in base.items() if code in index_of}
    for sid, store in data["stores"].items():
        key = f"{name}|{sid}"
        code, city_name = resolve_city(store.get("city"))
        point = None
        if not code:
            code, city_name, point = guess_city(key, name, store)
            if not code:
                skipped["no city"] += 1
                continue
        point = point or locate(key, store, code, city_name)
        if not point:
            skipped["no location"] += 1
            continue
        sub = store["sub"]
        base, delta, own = data["base"].get(sub, {}), {}, data["diff"].get(sid, {})
        for item, price in own.items():
            if item in index_of:
                delta[index_of[item]] = price
        for index, codes in generic_codes[name].items():
            for item in codes:
                price = own.get(item, base.get(item, 0))
                if price:
                    delta[index] = price
                    products[index][4] += 1
                    break
        entry = {
            "k": key,
            "ch": name,
            "b": f"{name}|{sub}",
            "n": store.get("name", ""),
            "a": store.get("addr", ""),
            "ll": point[:2],
            "d": delta,
        }
        if point[2]:
            entry["x"] = 1
        cities[code]["stores"].append(entry)
        cities[code]["name"] = city_name or cities[code].get("name", "")
        cities[code]["bases"][f"{name}|{sub}"] = base_index.get(sub, {})

for index in range(offset):
    products[index][5] = sum(1 for name in chains if index in generic_codes[name])

site = "site"
shutil.rmtree(site, ignore_errors=True)
os.makedirs(site + "/city")
os.makedirs(site + "/chains")


def dump(path, value):
    with open(os.path.join(site, path), "w", encoding="utf8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
    return os.path.getsize(os.path.join(site, path))


city_index, sizes = [], []
for code, city in cities.items():
    points = [store["ll"] for store in city["stores"]]
    center = [round(sum(p[0] for p in points) / len(points), 5), round(sum(p[1] for p in points) / len(points), 5)]
    name = city.get("name") or localities.get(code, "")
    if not name:
        skipped["city without a name"] += len(points)
        continue
    sizes.append(dump(f"city/{code}.json", {"c": code, "n": name, "stores": city["stores"], "bases": city["bases"]}))
    city_index.append(
        {
            "c": code,
            "n": name,
            "ll": center,
            "r": round(max(distance(center, p) for p in points), 1),
            "s": len(points),
            "ch": sorted({store["ch"] for store in city["stores"]}),
        }
    )
city_index.sort(key=lambda city: -city["s"])

dump("products.json", products)
dump("cities.json", city_index)
dump("chains.json", {name: {"name": CONFIG["names"].get(name, chains[name].get("chain_name") or name), "date": chains[name].get("date")} for name in chains})
dump("geo.json", geo)
dump("localities.json", localities)
for name in chains:
    source = f"art/{name}.json.gz"
    if os.path.exists(source):
        shutil.copy(source, f"{site}/chains/{name}.json.gz")
    else:
        with gzip.open(f"{site}/chains/{name}.json.gz", "wt", encoding="utf8") as handle:
            json.dump(chains[name], handle, ensure_ascii=False, separators=(",", ":"))

STATUS.update(
    {
        "cities": len(city_index),
        "stores": sum(city["s"] for city in city_index),
        "approx_locations": sum(1 for city in cities.values() for store in city["stores"] if store.get("x")),
        "skipped": dict(skipped),
        "geocode_requests": used,
        "city_file_kb": {"max": round(max(sizes) / 1024) if sizes else 0, "total": round(sum(sizes) / 1024)},
        "products_kb": round(os.path.getsize(site + "/products.json") / 1024),
        "generics_found": {GENERICS[i]["id"]: products[i][4] for i in range(offset)},
        "top_cities": [[city["n"], city["s"]] for city in city_index[:15]],
    }
)
dump("status.json", STATUS)
os.makedirs("status", exist_ok=True)
shutil.copy(site + "/status.json", "status/status.json")
sample = CONFIG.get("sample_city")
if sample:
    os.makedirs("sample/city", exist_ok=True)
    for path in ("products.json", "cities.json", "chains.json"):
        shutil.copy(f"{site}/{path}", f"sample/{path}")
    for code in str(sample).split(","):
        if os.path.exists(f"{site}/city/{code}.json"):
            shutil.copy(f"{site}/city/{code}.json", f"sample/city/{code}.json")
print(json.dumps(STATUS, ensure_ascii=False)[:3000])
