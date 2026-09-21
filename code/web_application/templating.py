"""Shared Jinja2Templates instance, used by every page router."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

# Absolute path, resolved from this file's location - a plain relative
# "templates" string depends on the *process's* working directory when
# uvicorn was launched, which changes depending on where you run it from
# and breaks with TemplateNotFound.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
