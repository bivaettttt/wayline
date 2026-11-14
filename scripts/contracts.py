import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

with TemporaryDirectory() as directory:
    os.environ["PROVIDER_DB"] = directory + "/provider.sqlite"
    from wayline.api import app

    from provider.app import app as provider

for name, service in (("openapi", app), ("provider-openapi", provider)):
    path = Path(f"docs/{name}.json")
    expected = (
        json.dumps(service.openapi(), ensure_ascii=False, sort_keys=True, indent=2)
        + "\n"
    )
    if "--write" in sys.argv:
        path.write_text(expected)
    else:
        assert path.read_text() == expected, path
if "--write" not in sys.argv:
    secrets = re.compile(
        rb"gh[pous]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    )
    for entry in (
        subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0")
    ):
        if not entry:
            continue
        path = Path(entry)
        content = path.read_bytes()
        assert path.name != ".env" and not secrets.search(content), path
        if path.suffix == ".md":
            for link in re.findall(r"\]\(([^)]+)\)", content.decode()):
                local = link.partition("#")[0]
                assert not local or "://" in local or (path.parent / local).exists(), (
                    path,
                    local,
                )
