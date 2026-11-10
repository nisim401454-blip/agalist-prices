"""Prints the list of chains for the nightly matrix (read from config.json)."""
import json, os

config = json.load(open("config.json", encoding="utf8"))
with open(os.environ.get("GITHUB_OUTPUT", "/dev/stdout"), "a", encoding="utf8") as out:
    out.write("chains=" + json.dumps(config["chains"]) + "\n")
