"""Local-only launcher; opening the public tunnel is a separate explicit command."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / ".secrets" / "image-attachment-probe"
TOKEN = STATE / "bearer-token"
PORT = 8002


def prepare():
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    if not TOKEN.exists():
        with open(TOKEN, "x", opener=lambda path, flags: os.open(path, flags, 0o600)) as handle:
            handle.write(secrets.token_urlsafe(32) + "\n")
    TOKEN.chmod(0o600)
    if not (STATE / "attachment-probe.png").exists():
        subprocess.run([sys.executable, "-m", "scripts.investigation.image_attachment_probe.fixture",
                        str(STATE)], cwd=ROOT, check=True)


async def check():
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    base = f"http://127.0.0.1:{PORT}"
    async with httpx2.AsyncClient(trust_env=False, timeout=5) as http:
        health = await http.get(base + "/health")
        health.raise_for_status()
        denied = await http.post(base + "/mcp", json={})
        if denied.status_code != 401:
            raise RuntimeError("Expected unauthenticated MCP request to be denied.")
    async with httpx2.AsyncClient(trust_env=False, timeout=5,
            headers={"Authorization": "Bearer " + TOKEN.read_text().strip()}) as http:
        async with Client(streamable_http_client(base + "/mcp", http_client=http)) as client:
            listed = await client.list_tools()
            if [t.name for t in listed.tools] != ["inspect_attached_image"]:
                raise RuntimeError("Unexpected tool list; port may belong to another service.")
            result = await client.call_tool("inspect_attached_image", {"image_reference": None})
            if result.is_error or result.structured_content.get("status") != "no_reference":
                raise RuntimeError("Unexpected null probe result.")
    print(json.dumps({"health": "ok", "unauthenticated": "denied",
                      "tool": "inspect_attached_image", "null_probe": "no_reference"}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "serve", "check", "tunnel", "copy-token"])
    parser.add_argument("--allowed-host", help="Exact image storage hostname; serve only")
    args = parser.parse_args()
    if args.allowed_host and args.command != "serve":
        parser.error("--allowed-host is only valid with serve")
    prepare()
    if args.command == "prepare":
        print(f"Ready. Fixture: {STATE / 'attachment-probe.png'}\nSecret stored privately; no network listeners started.")
    elif args.command == "serve":
        os.environ.update(PROBE_BEARER_TOKEN=TOKEN.read_text().strip(),
                          PROBE_ALLOWED_HOST=args.allowed_host or "", HOST="127.0.0.1", PORT=str(PORT))
        import uvicorn
        from .server import create_app
        print(f"Probe listening locally on 127.0.0.1:{PORT}; "
              + ("retrieval enabled for the configured host." if args.allowed_host else "classification only."), flush=True)
        uvicorn.run(create_app(), host="127.0.0.1", port=PORT, access_log=False, log_level="critical")
    elif args.command == "check":
        asyncio.run(check())
    elif args.command == "copy-token":
        if sys.platform != "darwin":
            parser.error(f"Clipboard helper requires macOS; read the private token file at {TOKEN}")
        subprocess.run(["/usr/bin/pbcopy"], input=TOKEN.read_bytes().strip(), check=True)
        print("Probe token copied to clipboard. Paste only in the test connector's bearer-token field.")
    else:
        asyncio.run(check())
        binary = STATE / "bin" / "cloudflared"
        if not binary.is_file():
            parser.error("Local cloudflared binary is missing; see README.md for installation.")
        # An explicit empty config avoids reading a user's unrelated tunnel setup.
        config = STATE / "tunnel-config.yml"
        config.write_text("{}\n")
        command = [str(binary), "tunnel", "--config", str(config), "--no-autoupdate",
                   "--url", f"http://127.0.0.1:{PORT}", "--http-host-header", f"127.0.0.1:{PORT}"]
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith(("TUNNEL_", "PROBE_"))}
        print("Opening a public HTTPS tunnel to the authenticated test probe. Ctrl-C closes it.", flush=True)
        os.execve(binary, command, environment)


if __name__ == "__main__":
    main()
