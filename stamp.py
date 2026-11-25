"""Runs just before a built site goes to GitHub Pages. Adds the publication details, so whatever is live
always describes itself: the time it was published, the date of its prices, and which chains rely on
older files. Writes site/updated.json (small, for the app) and adds the same to site/status.json.
If the publish fails, none of this goes live and the previous files stay as they were."""
import collections, datetime, json, os, zoneinfo

IL = zoneinfo.ZoneInfo("Asia/Jerusalem")
site = os.environ.get("SITE_DIR", "site")
status = json.load(open(f"{site}/status.json", encoding="utf8"))
names = json.load(open("config.json", encoding="utf8"))["names"]
now = datetime.datetime.now(datetime.timezone.utc)

chains = status.get("chains") or {}
fresh_dates = [entry["date"] for entry in chains.values() if entry.get("state") == "fresh" and entry.get("date")]
# the date most chains' files carry: the date of "these prices"
prices_date = collections.Counter(fresh_dates).most_common(1)[0][0] if fresh_dates else None
older = []
for name, entry in chains.items():
    if entry.get("state") in ("missing", "expired"):
        older.append({"chain": name, "name": names.get(name, name), "date": entry.get("date"), "state": entry["state"], "shown": False})
    elif entry.get("state") != "fresh" or (prices_date and entry.get("date") and entry["date"] < prices_date):
        older.append({"chain": name, "name": names.get(name, name), "date": entry.get("date"), "state": "stale", "shown": True})

updated = {
    "published_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "published_il": now.astimezone(IL).strftime("%Y-%m-%d %H:%M"),
    "prices_date": prices_date,
    "built_at": status.get("built"),
    "build_run": os.environ.get("SOURCE_RUN"),
    "publish_run": os.environ.get("GITHUB_RUN_ID"),
    "schedule": "weekly, Sunday",
    "older_chains": older,
}
status.update({"published_at": updated["published_at"], "prices_date": prices_date, "build_run": updated["build_run"],
               "publish_run": updated["publish_run"], "older_chains": older})
for path, value in ((f"{site}/updated.json", updated), (f"{site}/status.json", status)):
    with open(path, "w", encoding="utf8") as handle:
        json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
print(json.dumps(updated, ensure_ascii=False))
