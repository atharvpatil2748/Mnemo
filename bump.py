import os

FILES = [
    "mnemo-core/mnemo/__init__.py",
    "mnemo-server/mnemo_server/__init__.py",
    "pyproject.toml",
    "mnemo-core/pyproject.toml",
    "mnemo-server/pyproject.toml",
    "mnemo-ui/package.json",
]

OLD_VERSION = "0.10.3"
NEW_VERSION = "0.10.4"

for fpath in FILES:
    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            content = f.read()

        content = content.replace(OLD_VERSION, NEW_VERSION)

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Updated {fpath}")
    else:
        print(f"File {fpath} not found")
