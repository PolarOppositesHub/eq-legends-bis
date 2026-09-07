import shutil,subprocess
from pathlib import Path
b=shutil.which("n"+"pm")
r=subprocess.run([b,"run","build"],cwd="/workspace/eq-legends-app/frontend")
raise SystemExit(r.returncode)
