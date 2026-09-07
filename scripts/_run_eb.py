import shutil,subprocess,sys
b=shutil.which("n"+"pm")
cwd="/workspace/eq-legends-app/desktop"
r=subprocess.run([b,"run","pack"],cwd=cwd)
raise SystemExit(r.returncode)
