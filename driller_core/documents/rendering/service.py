from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from jinja2 import Environment, FileSystemLoader, select_autoescape


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_ROOT = DOCUMENTS_ROOT / "templates"
STYLES_ROOT = DOCUMENTS_ROOT / "styles"

_environment = Environment(
    loader=FileSystemLoader(str(TEMPLATES_ROOT)),
    autoescape=select_autoescape(("html", "xml")),
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_html(template_name: str, context: dict[str, Any]) -> str:
    template = _environment.get_template(template_name)
    return template.render(**context)


def render_pdf_from_html(
    html: str,
    *,
    base_url: str | Path | None = None,
    stylesheet_paths: Iterable[str | Path] | None = None,
) -> bytes:
    from weasyprint import CSS, HTML

    stylesheets = [CSS(filename=str(path)) for path in (stylesheet_paths or ())]
    return HTML(string=html, base_url=str(base_url or PROJECT_ROOT)).write_pdf(stylesheets=stylesheets)

