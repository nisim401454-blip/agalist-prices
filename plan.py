"""Prints the list of chains for the nightly matrix (read from config.json).
A scheduled run is skipped when today's publication is already healthy and complete,
so several scheduled attempts a day cost nothing once one of them has succeeded."""
import datetime, json, os

config = json.load(open("config.json", encoding="utf8"))
skip = False
if os.environ.get("GITHUB_EVENT_NAME") == "schedule":
    try:
        status = json.load(open("status/status.json", encoding="utf8"))
        health = status.get("health") or {}
        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        skip = status["built"][:10] == today and bool(health.get("ok")) and bool(health.get("complete"))
    except (OSError, ValueError, KeyError):
        skip = False
with open(os.environ.get("GITHUB_OUTPUT", "/dev/stdout"), "a", encoding="utf8") as out:
    out.write("chains=" + json.dumps(config["chains"]) + "\n")
    out.write("skip=" + ("true" if skip else "false") + "\n")
print("skip" if skip else "run")
