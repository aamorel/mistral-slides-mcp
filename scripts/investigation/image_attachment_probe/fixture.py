"""Generate a disposable PNG and local comparison evidence."""
import argparse
import json
import secrets
from pathlib import Path

from PIL import Image
from .probe import inspect_bytes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (317, 193), "navy")
    image.paste("orange", (0, 0, 158, 96))
    image.paste("lime", (158, 96, 317, 193))
    image.paste(Image.frombytes("RGB", (32, 32), secrets.token_bytes(32 * 32 * 3)), (140, 80))
    path = args.directory / "attachment-probe.png"
    if path.exists():
        parser.error("Fixture already exists; choose a new directory to preserve its hashes.")
    image.save(path)
    (args.directory / "expected.json").write_text(json.dumps(inspect_bytes(path.read_bytes()), indent=2) + "\n")
    print(f"Fixture: {path}\nComparison: {args.directory / 'expected.json'}")


if __name__ == "__main__":
    main()
