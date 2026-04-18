"""
Netlify serverless function — wraps the FastAPI app via Mangum.

Netlify Functions run on AWS Lambda. Mangum adapts the ASGI interface
(FastAPI/Starlette) to the Lambda event/context interface.

Deploy steps:
  1. Push this repo to GitHub.
  2. Connect the repo in Netlify (Import project → GitHub).
  3. Netlify reads netlify.toml and runs the build command.
  4. All requests not matched by /static/* are proxied here.

Environment variables needed (set in Netlify UI → Site settings → Env vars):
  OPENAI_API_KEY   — for AI generation features
  AF_PROJECTS_DIR  — optional, path to projects directory (default: ./projects)
"""
import sys
import os
from pathlib import Path

# Make the src package importable
sys.path.insert(0, str(Path(__file__).parents[3] / "src"))

from mangum import Mangum
from augmented_fiction.web.app import app

handler = Mangum(app, lifespan="off")
