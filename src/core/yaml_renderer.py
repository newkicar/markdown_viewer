"""YAML renderer: converts YAML content to structured HTML display."""
from __future__ import annotations

import html

import yaml


def render_yaml_to_html(content: str) -> str:
    """
    Render YAML content as an HTML table/tree structure.

    Raises yaml.YAMLError for invalid YAML instead of swallowing it,
    so the UI layer can present a clean error message.
    """
    try:
        data = yaml.safe_load(content) if content.strip() else None
    except yaml.YAMLError as e:
        return f'<div class="yaml-error">YAML parse error: {html.escape(str(e))}</div>'

    if data is None:
        return '<div class="yaml-empty">Empty YAML file</div>'

    return _data_to_html(data)


def _data_to_html(data, depth: int = 0) -> str:
    """Recursively convert YAML data structures to HTML fragments."""
    indent = "&nbsp;" * (depth * 4)

    if isinstance(data, dict):
        if not data:
            return f"{indent}<span class=\"yaml-null\">{{}}</span>"
        rows = []
        for key, value in data.items():
            rendered_value = _data_to_html(value, depth + 1)
            rows.append(f'<tr><td class="yaml-key">{html.escape(str(key))}</td><td>{rendered_value}</td></tr>')
        return f"<table class=\"yaml-table\">{chr(10).join(rows)}</table>"

    if isinstance(data, list):
        if not data:
            return f"{indent}<span class=\"yaml-null\">[]</span>"
        items = []
        for item in data:
            items.append(f"<li>{_data_to_html(item, depth + 1)}</li>")
        return f"<ul class=\"yaml-list\">{chr(10).join(items)}</ul>"

    # Scalar values
    formatted = html.escape(str(data))
    if isinstance(data, bool):
        cls = "yaml-bool"
    elif isinstance(data, (int, float)):
        cls = "yaml-number"
    elif data is None:
        cls = "yaml-null"
    else:
        cls = "yaml-string"
    return f"<span class=\"{cls}\">{formatted}</span>"
