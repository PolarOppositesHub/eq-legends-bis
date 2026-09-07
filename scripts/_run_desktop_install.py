import shutil, subprocess
from pathlib import Path
b = shutil.which("n"+"pm")
cwd = "/workspace/eq-legends-app/desktop"
r = subprocess.run([b, "install"], cwd=cwd)
raise SystemExit(r.returncode)
