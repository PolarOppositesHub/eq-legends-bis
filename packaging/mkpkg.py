import json
from pathlib import Path
pkg=json.loads(Path("/workspace/eq-legends-app/package.json").read_text())
pkg["scripts"]={
print(123)
