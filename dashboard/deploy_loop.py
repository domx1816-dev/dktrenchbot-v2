#!/usr/bin/env python3
"""Regenerate dashboard and deploy to Cloudflare Pages every 60s"""
import os, sys, time, subprocess
from pathlib import Path

DASH = Path(__file__).parent
PROJ = "dktrenchbot"
TOKEN = "cfut_GXa99ala6yjfDGgfE2eR2a4t1IK30icR8Gq3JjAs16660743"
LOG = DASH / "deploy.log"

def log(msg):
    import datetime
    ts = datetime.datetime.utcnow().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def generate():
    sys.path.insert(0, str(DASH))
    import importlib, generate as gen_mod
    importlib.reload(gen_mod)
    gen_mod.main()

def deploy():
    env = os.environ.copy()
    env["CLOUDFLARE_API_TOKEN"] = TOKEN
    result = subprocess.run(
        ["npx", "wrangler", "pages", "deploy", ".", "--project-name", PROJ],
        cwd=str(DASH), capture_output=True, text=True, env=env, timeout=60
    )
    lines = (result.stdout + result.stderr).strip().split("\n")
    return next((l for l in reversed(lines) if l.strip()), "no output")

log("Deploy loop starting")
while True:
    try:
        generate()
        result = deploy()
        log(f"Deployed: {result}")
    except Exception as e:
        log(f"Error: {e}")
    time.sleep(60)
