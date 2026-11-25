"""Alerts for the weekly price update. Keeps at most two GitHub issues open:
- "עדכון המחירים דורש בדיקה": the weekly update did not go live (build or publish failed, too few fresh
  chains), or by Monday morning no publication happened this week at all (--watch).
- "רשת נשענת על נתונים ישנים": the live prices include a chain whose files are older than the rest.
Days without a run are expected and raise nothing. Early Sunday attempts stay quiet when they fail
(a later attempt may still succeed); the last Sunday attempt, a manual run and the Monday watch alert."""
import datetime, json, os, subprocess, sys, zoneinfo

TITLE = "עדכון המחירים דורש בדיקה"
STALE_TITLE = "רשת נשענת על נתונים ישנים"
IL = zoneinfo.ZoneInfo("Asia/Jerusalem")
LAST_SUNDAY_ATTEMPT_UTC = 16  # the 16:47 UTC cron in prices.yml
now = datetime.datetime.now(datetime.timezone.utc)
server, repo, run = (os.environ.get(k, "") for k in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
run_url = f"{server}/{repo}/actions/runs/{run}"
retry_hint = f"לניסיון פרסום חוזר בלי לאסוף מחדש: Actions > publish prices > Run workflow (אפשר להשאיר את המספר ריק). {server}/{repo}/actions/workflows/publish.yml"


def gh(*args):
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True).stdout.strip()
    except OSError as error:
        print("gh unavailable:", error)
        return ""


def open_issue(title):
    return gh("issue", "list", "--state", "open", "--search", f'"{title}" in:title', "--json", "number", "--jq", ".[0].number")


def raise_issue(title, lines):
    number, body = open_issue(title), "\n".join(lines)
    if number:
        gh("issue", "comment", number, "--body", body)
    else:
        gh("issue", "create", "--title", title, "--body", body)


def close_issue(title, text):
    number = open_issue(title)
    if number:
        gh("issue", "comment", number, "--body", text)
        gh("issue", "close", number)


def load(path):
    try:
        return json.load(open(path, encoding="utf8"))
    except (OSError, ValueError):
        return None


def older_lines(status):
    lines = []
    for entry in status.get("older_chains") or []:
        shown = "מוצגת עם המחירים הישנים" if entry.get("shown") else "לא מוצגת (חסרה או ישנה מדי)"
        lines.append(f"- {entry.get('name')} ({entry.get('chain')}): נתונים מ-{entry.get('date') or 'לא ידוע'}, {shown}")
    return lines


def report_older(status):
    lines = older_lines(status)
    if lines:
        raise_issue(STALE_TITLE, ["במחירים שבאוויר יש רשתות שנשענות על קובץ ישן יותר משאר הרשתות "
                                  f"(מחירי השבוע מ-{status.get('prices_date')}):", ""] + lines
                    + ["", "זו תקלה נפרדת בהורדה של הרשת. היא לא נפתרת מעצמה כשהפרסום מצליח.", f"הריצה: {run_url}"])
    else:
        close_issue(STALE_TITLE, f"כל הרשתות בפרסום האחרון עדכניות. הריצה: {run_url}")


def watch():
    """Monday morning: did this week's prices go live?"""
    status = load("status/status.json") or {}
    today = now.astimezone(IL).date()
    sunday = today - datetime.timedelta(days=(today.weekday() + 1) % 7)
    published = status.get("published_at")
    when = datetime.datetime.strptime(published, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).astimezone(IL) if published else None
    print("this week's Sunday:", sunday, "| last publication:", when)
    if when is None or when.date() < sunday:
        raise_issue(TITLE, ["העדכון השבועי לא פורסם השבוע.",
                            f"הפרסום המוצלח האחרון: {when.strftime('%d.%m.%Y %H:%M') if when else 'לא ידוע'}. באתר נשארים המחירים שלו.",
                            "", f"לעדכון עכשיו: Actions > weekly prices > Run workflow. {server}/{repo}/actions/workflows/prices.yml",
                            f"בדיקת השבוע: {run_url}"])
        sys.exit(1)
    if older_lines(status):
        report_older(status)


def after_publish():
    final = os.environ.get("TRIGGER") != "schedule" or now.hour >= LAST_SUNDAY_ATTEMPT_UTC
    problems = []
    steps = [("BUILD", "איסוף ובנייה"), ("SOURCE", "איתור האתר הבנוי"), ("DOWNLOAD", "הורדת האתר הבנוי"),
             ("PAGES", "הכנת קובצי הפרסום"), ("DEPLOY", "פרסום ל-GitHub Pages")]
    for key, label in steps:
        outcome = os.environ.get(key + "_OUTCOME", "success") or "skipped"
        if outcome != "success":
            problems.append(f"השלב '{label}' הסתיים במצב {outcome}")
            break  # the steps after the first failure are skipped; the first one is the cause
    live = os.environ.get("DEPLOY_OUTCOME") == "success"
    status = load("site/status.json") or {}
    health = status.get("health") or {}
    if status and not health.get("ok"):
        problems += health.get("problems") or ["בדיקת האיכות של הבנייה לא עברה"]
    published = load("status/status.json") or {}
    print("problems:", problems, "| live:", live, "| final attempt:", final)

    if problems:
        if final:
            lines = ["עדכון המחירים השבועי לא הסתיים במצב תקין.", "", "מה נמצא:"] + [f"- {p}" for p in problems]
            if not live:
                lines += ["", f"באתר נשארו המחירים מהפרסום המוצלח האחרון ({published.get('prices_date') or 'לא ידוע'}, "
                              f"פורסם {published.get('published_at') or 'לא ידוע'})."]
                if os.environ.get("BUILD_OUTCOME") == "success" and os.environ.get("SOURCE_OUTCOME", "success") == "success":
                    lines += [retry_hint]
            raise_issue(TITLE, lines + ["", f"הריצה: {run_url}"])
            sys.exit(1)
        print("not the last Sunday attempt: staying quiet, a later attempt may still succeed")
        sys.exit(0)
    close_issue(TITLE, f"העדכון השבועי פורסם בהצלחה. הריצה: {run_url}")
    if live:
        report_older(status)


watch() if "--watch" in sys.argv else after_publish()
