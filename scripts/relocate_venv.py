"""Repair Windows venv launchers after a project-directory rename.

Run with a tooling Python providing pip's bundled distlib, not the application
Python. Entry points are captured by the original environment before the move.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_root")
    parser.add_argument("new_root")
    parser.add_argument("entrypoints")
    args = parser.parse_args()
    old_root = Path(args.old_root)
    new_root = Path(args.new_root).resolve(strict=True)
    scripts = new_root / ".venv" / "Scripts"
    executable = scripts / "python.exe"
    if not executable.is_file() or not scripts.resolve().is_relative_to(new_root):
        raise RuntimeError("Expected a Windows project venv inside the new directory")

    from pip._vendor.distlib.scripts import ScriptMaker

    entries = json.loads(Path(args.entrypoints).read_text(encoding="utf-8"))
    for entry in entries:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", entry["name"]):
            raise RuntimeError("Invalid console entry-point name")
    maker = ScriptMaker(None, str(scripts))
    maker.executable = str(executable)
    maker.clobber = True
    maker.variants = {""}
    for entry in entries:
        maker.make(
            f"{entry['name']} = {entry['value']}",
            options={"gui": entry["group"] == "gui_scripts"},
        )
    for path in scripts.glob("activate*"):
        if path.is_file() and path.suffix != ".exe":
            text = path.read_text(encoding="utf-8")
            text = text.replace(str(old_root), str(new_root))
            text = text.replace("supermew", "wenxi")
            path.write_text(text, encoding="utf-8")
    config = new_root / ".venv" / "pyvenv.cfg"
    text = config.read_text(encoding="utf-8")
    config.write_text(
        re.sub(r"(?m)^prompt = .+$", "prompt = wenxi", text), encoding="utf-8"
    )
    print(f"Rebuilt {len(entries)} installed entry points; activation prompt: wenxi")


if __name__ == "__main__":
    main()
