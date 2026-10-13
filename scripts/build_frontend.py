"""Build a React SPA into Vercel's CDN-served public directory."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT, check=True)
subprocess.run(["npm", "run", "build"], cwd=ROOT, check=True)
shutil.copy(ROOT / "frontend/static/favicon.svg", ROOT / "public/favicon.svg")
