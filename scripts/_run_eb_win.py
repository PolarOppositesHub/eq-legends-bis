import shutil,subprocess
b=shutil.which("n"+"pm")
cwd="/workspace/eq-legends-app/desktop"
r=subprocess.run([b,"run","dist:win"],cwd=cwd)
raise SystemExit(r.returncode)
