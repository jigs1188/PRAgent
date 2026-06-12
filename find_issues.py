import sys
sys.stdout.reconfigure(encoding="utf-8")
import requests

# Get ALL recent issues (any label)
print("=== ALL RECENT OPEN ISSUES ===")
url = "https://api.github.com/repos/spf13/cobra/issues?state=open&per_page=20&sort=updated"
r = requests.get(url, timeout=15)
for i in r.json():
    if not i.get("pull_request"):
        labels = ", ".join(l["name"] for l in i.get("labels", []))
        print(f"  #{i['number']:>5}  [{labels or 'none'}]  {i['title'][:80]}")

print("\n=== RECENTLY CLOSED ISSUES (with accepted PRs for validation) ===")
url = "https://api.github.com/repos/spf13/cobra/issues?state=closed&per_page=30&sort=updated&direction=desc"
r = requests.get(url, timeout=15)
count = 0
for i in r.json():
    if not i.get("pull_request") and count < 15:
        labels = ", ".join(l["name"] for l in i.get("labels", []))
        print(f"  #{i['number']:>5}  [{labels or 'none'}]  {i['title'][:80]}")
        count += 1
