"""First job of every price run. Prints the chain list for the matrix and decides whether to skip:
- any trigger: skip when another price run is already active, so a manual refresh never opens a second one;
- a scheduled Sunday attempt: skip when this week's publication already went live and is healthy,
  so the backup attempts later on Sunday cost nothing once the first one has succeeded."""
import datetime, json, os, urllib.request, zoneinfo

IL = zoneinfo.ZoneInfo("Asia/Jerusalem")
config = json.load(open("config.json", encoding="utf8"))
event = os.environ.get("GITHUB_EVENT_NAME", "")
reason = ""


def active_runs():
    """Other runs of this workflow that are queued or running (the API answers per status)."""
    repo, token, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GH_TOKEN"), os.environ.get("GITHUB_RUN_ID")
    workflow = os.environ.get("WORKFLOW_FILE", "prices.yml")
    if not repo or not token:
        return []
    found = []
    for state in ("in_progress", "queued", "waiting", "pending"):
        url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?status={state}&per_page=20"
        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        try:
            runs = json.loads(urllib.request.urlopen(request, timeout=20).read())["workflow_runs"]
        except Exception as error:  # a failed check must not block the update
            print("could not list active runs:", str(error)[:120])
            continue
        found += [run["html_url"] for run in runs if str(run["id"]) != str(run_id)]
    return found


others = active_runs()
if others:
    reason = "another price run is already active: " + others[0]

if not reason and event == "schedule":
    try:
        status = json.load(open("status/status.json", encoding="utf8"))  # committed only after a successful publish
        published = datetime.datetime.strptime(status["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
        health = status.get("health") or {}
        today = datetime.datetime.now(IL).date()
        if published.astimezone(IL).date() == today and health.get("ok") and health.get("complete"):
            reason = "this week's prices were already published today"
    except (OSError, ValueError, KeyError):
        pass

with open(os.environ.get("GITHUB_OUTPUT", "/dev/stdout"), "a", encoding="utf8") as out:
    out.write("chains=" + json.dumps(config["chains"]) + "\n")
    out.write("skip=" + ("true" if reason else "false") + "\n")
if reason and os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf8") as summary:
        summary.write(f"דילוג: {reason}\n")
print("skip:", reason if reason else "no, running")
