import hashlib
import json
import pathlib
import re

p = pathlib.Path("meridian/migrations")
files = sorted(p.glob("versions/*.py"))
m = {}
for f in files:
    if f.name == "__init__.py":
        continue
    match = re.search(r'revision\s*=\s*"([^"]+)"', f.read_text())
    if match:
        rev = match.group(1)
        digest = hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        m[rev] = digest

(p / "CHECKSUMS.json").write_text(json.dumps(m, indent=2) + "\n")
print("Updated CHECKSUMS.json with", len(m), "entries.")
