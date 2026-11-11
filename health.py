"""Last step of every run: decides whether the publication is trustworthy and keeps one GitHub issue
open while it is not. Early scheduled attempts stay quiet (a later attempt may still succeed); the
last attempt of the day, a manual run or a code push raise the alarm and fail the run."""
import datetime, json, os, subprocess, sys

TITLE = "עדכון המחירים דורש בדיקה"
now = datetime.datetime.now(datetime.timezone.utc)
final = os.environ.get("GITHUB_EVENT_NAME") != "schedule" or now.hour >= 12
run_url = "{}/{}/actions/runs/{}".format(os.environ.get("GITHUB_SERVER_URL", ""), os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_RUN_ID", ""))

problems, status = [], {}
for step in ("BUILD", "PAGES", "DEPLOY"):
    outcome = os.environ.get(step + "_OUTCOME", "success")
    if outcome != "success":
        problems.append(f"השלב {step.lower()} הסתיים במצב {outcome}")
try:
    status = json.load(open("status/status.json", encoding="utf8"))
    built = datetime.datetime.strptime(status["built"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    if (now - built).total_seconds() > 3 * 3600:
        problems.append(f"קובץ הסטטוס לא התעדכן בריצה הזו (נבנה {status['built']})")
    health = status.get("health") or {}
    if not health.get("ok"):
        problems += health.get("problems") or ["הבדיקה לא עברה"]
except (OSError, ValueError, KeyError) as error:
    problems.append(f"אין קובץ סטטוס קריא: {error}")

lines = []
for name, entry in (status.get("chains") or {}).items():
    if entry.get("state") != "fresh":
        lines.append(f"- {name}: {entry.get('state')}, נתונים מ-{entry.get('data_to') or entry.get('date')}, מקור {entry.get('source')}")


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


found = gh("issue", "list", "--state", "open", "--search", f'"{TITLE}" in:title', "--json", "number", "--jq", ".[0].number")
number = found.stdout.strip()
print("problems:", problems, "| final attempt:", final, "| open issue:", number or "-")

if problems and final:
    body = "\n".join(["עדכון המחירים האוטומטי לא הסתיים במצב תקין.", "", "מה נמצא:"] + [f"- {p}" for p in problems]
                     + (["", "רשתות שאינן טריות:"] + lines if lines else []) + ["", f"הריצה: {run_url}"])
    if number:
        print(gh("issue", "comment", number, "--body", body).stderr)
    else:
        print(gh("issue", "create", "--title", TITLE, "--body", body).stderr)
    sys.exit(1)
if not problems and number:
    gh("issue", "comment", number, "--body", f"העדכון חזר לתקין. הריצה: {run_url}")
    gh("issue", "close", number)
