#!/usr/bin/env bash
# Commit data when it changed, or when the last commit is over 20 h old.
DO_COMMIT=$(python - <<'PY'
import json, hashlib, os, subprocess, time
d = json.load(open("data/storms.json")); d.pop("generated", None)
h = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()
old = open("data/.hash").read().strip() if os.path.exists("data/.hash") else ""
last = int(subprocess.run(["git", "log", "-1", "--format=%ct"], capture_output=True, text=True).stdout or 0)
open("data/.hash", "w").write(h)
print("1" if (h != old or time.time() - last > 20 * 3600) else "0")
PY
)
if [ "$DO_COMMIT" = "1" ]; then
  git add data latest.png
  if git commit -q -m "Storm update $(date -u +%Y-%m-%dT%H:%MZ)"; then
    git pull --rebase -q && git push -q && echo "::notice title=Commit::pushed storm update"
  fi
else
  git checkout -q -- data latest.png 2>/dev/null || true
  echo "::notice title=Commit::no change in storm data"
fi
