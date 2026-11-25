"""Finds the price run whose built site should be published: the run given by hand (RUN_ID), or else the
newest "weekly prices" run that still has an unexpired "site" artifact."""
import json, os, sys, urllib.request

repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"]
wanted = (os.environ.get("RUN_ID") or "").strip().rstrip("/").split("/")[-1]  # a run number or a pasted run link


def api(path):
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}",
                                     headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    return json.loads(urllib.request.urlopen(request, timeout=30).read())


def has_site(run_id):
    artifacts = api(f"actions/runs/{run_id}/artifacts?name=site")["artifacts"]
    return any(not artifact["expired"] for artifact in artifacts)


if wanted and wanted == os.environ.get("GITHUB_RUN_ID"):
    run_id = wanted  # called right after this run's own build
elif wanted:
    if not has_site(wanted):
        sys.exit(f"run {wanted} has no built site to publish (the build failed, or the site artifact expired after 14 days)")
    run_id = wanted
else:
    run_id = next((str(run["id"]) for run in api("actions/workflows/prices.yml/runs?per_page=30")["workflow_runs"] if has_site(run["id"])), "")
    if not run_id:
        sys.exit("no recent price run has a built site; run 'weekly prices' instead")
print("publishing the site built by run", run_id)
with open(os.environ.get("GITHUB_OUTPUT", "/dev/stdout"), "a", encoding="utf8") as out:
    out.write(f"run_id={run_id}\n")
