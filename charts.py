"""
Vega-Lite chart rendering with bundled JS for CSP-compliant SiS deployment.

SiS enforces a Content Security Policy that blocks external ``<script>`` tags.
To work around this, the Vega libraries (``vega``, ``vega-lite``, ``vega-embed``,
``vega-interpreter``) are loaded from local ``js/`` files and inlined into a
self-contained HTML document rendered via ``streamlit.components.html()``.

All chart specs have VALD dark-theme colours forced onto every axis, legend,
title, mark, and text element via ``_force_encoding_axis_colors()`` before
rendering, so charts always match the app's brand palette regardless of what
the Cortex Agent returns.
"""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from config import (
    VALD_DARK,
    VALD_GRAY,
    VALD_ORANGE,
    VALD_WHITE,
)

# Chart sizing defaults
_DEFAULT_CHART_HEIGHT = 300
_DEFAULT_CHART_WIDTH = 420
_VCONCAT_ROW_SPACING = 30
_CONCAT_MAX_COLUMNS = 2
_CHART_PADDING_ESTIMATE = 160  # title + legend + axes + container padding
_IFRAME_EXTRA_PX = 10


@st.cache_resource
def _load_vega_libs() -> dict[str, str]:
    """Load bundled Vega JS libraries into memory once per container lifecycle."""
    base = os.path.join(os.path.dirname(__file__), "js")
    libs = {}
    for name in ["vega.min.js", "vega-lite.min.js", "vega-embed.min.js", "vega-interpreter.min.js"]:
        with open(os.path.join(base, name), encoding="utf-8") as f:
            libs[name] = f.read()
    return libs


_CHART_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script>{vega_js}</script>
<script>{vega_lite_js}</script>
<script>{vega_embed_js}</script>
<script>{vega_interpreter_js}</script>
</head>
<body style="margin:0;padding:0;overflow:hidden;background:{bg_color}">
<div id="chart" style="width:100%"></div>
<script>
vegaEmbed('#chart', {spec_json}, {{
  ast: true,
  expr: vega.expressionInterpreter,
  actions: false,
  renderer: 'canvas'
}}).then(function(result) {{
  var chartEl = document.getElementById('chart');
  if (chartEl) {{
    // Center chart canvas if it fits within the container
    var canvas = document.querySelector('#chart canvas');
    if (canvas && canvas.width < chartEl.offsetWidth) {{
      canvas.style.display = 'block';
      canvas.style.margin = '0 auto';
    }}
    // One-shot: set final iframe height after Vega render settles.
    // Uses rAF to measure after the browser completes layout, then
    // compensates parent scroll position so the user is not shifted.
    requestAnimationFrame(function() {{
      var h = chartEl.offsetHeight;
      if (h > 0 && window.frameElement) {{
        var frame = window.frameElement;
        var oldH = frame.offsetHeight;
        if (Math.abs(h - oldH) > 2) {{
          var main = window.parent.document.querySelector('[data-testid="stAppScrollToBottomContainer"]')
                  || window.parent.document.querySelector('section.stMain')
                  || window.parent.document.querySelector('section.main');
          var compensate = false;
          if (main) {{
            var rect = frame.getBoundingClientRect();
            var mainRect = main.getBoundingClientRect();
            compensate = (rect.bottom < mainRect.top);
          }}
          frame.style.height = h + 'px';
          if (compensate && main) {{
            main.scrollTop += (h - oldH);
          }}
        }}
      }}
    }});
  }}
}}).catch(function(err) {{
  document.getElementById('chart').innerHTML =
    '<p style="color:#ff6b6b;font-family:sans-serif;padding:1rem;">Chart error: ' +
    err.message + '</p>';
  console.error(err);
}});
</script>
</body></html>"""


@st.cache_data(show_spinner=False)
def _build_chart_html(spec_json: str) -> str:
    """Build self-contained HTML with inlined Vega JS for a chart spec. Cached across all users."""
    libs = _load_vega_libs()
    return _CHART_HTML_TEMPLATE.format(
        vega_js=libs["vega.min.js"],
        vega_lite_js=libs["vega-lite.min.js"],
        vega_embed_js=libs["vega-embed.min.js"],
        vega_interpreter_js=libs["vega-interpreter.min.js"],
        spec_json=spec_json,
        bg_color=VALD_DARK,
    )


def render_vega_chart(spec: dict[str, Any] | str, height: int | None = None) -> None:
    """Render a Vega-Lite spec via components.html() with VALD dark theme forcing."""
    if isinstance(spec, str):
        spec = json.loads(spec)

    # Compute a tight iframe height from the spec instead of a fixed 900px.
    if height is None:
        chart_h = spec.get("height", _DEFAULT_CHART_HEIGHT)
        if isinstance(chart_h, str):  # "container" or other string values
            chart_h = _DEFAULT_CHART_HEIGHT + 100
        # For vconcat / concat, sum up sub-spec heights
        if "vconcat" in spec and isinstance(spec["vconcat"], list):
            sub_heights = [s.get("height", _DEFAULT_CHART_HEIGHT) for s in spec["vconcat"] if isinstance(s, dict)]
            chart_h = sum(h if isinstance(h, (int, float)) else _DEFAULT_CHART_HEIGHT for h in sub_heights)
            chart_h += _VCONCAT_ROW_SPACING * (len(spec["vconcat"]) - 1)
        elif "concat" in spec and isinstance(spec["concat"], list):
            sub_heights = [s.get("height", _DEFAULT_CHART_HEIGHT) for s in spec["concat"] if isinstance(s, dict)]
            sub_heights = [h if isinstance(h, (int, float)) else _DEFAULT_CHART_HEIGHT for h in sub_heights]
            rows = (len(sub_heights) + 1) // _CONCAT_MAX_COLUMNS
            max_per_row = max(sub_heights[:_CONCAT_MAX_COLUMNS]) if sub_heights else _DEFAULT_CHART_HEIGHT
            chart_h = max_per_row * rows + _VCONCAT_ROW_SPACING * (rows - 1)
        height = int(chart_h + _CHART_PADDING_ESTIMATE)

    # --- data_to_chart specs lack explicit width; size to ~50% of chat area ---
    if "width" not in spec and not any(k in spec for k in ("vconcat", "hconcat", "concat", "facet")):
        spec["width"] = _DEFAULT_CHART_WIDTH

    # Force chart background to match VALD dark theme
    spec["background"] = VALD_DARK
    config = spec.setdefault("config", {})
    config["background"] = VALD_DARK
    config.setdefault("view", {}).update({"stroke": "transparent", "fill": VALD_DARK})
    # Force axis colors
    axis_cfg = config.setdefault("axis", {})
    axis_cfg.update({
        "domainColor": "#3a3d40",
        "gridColor": "#2f3234",
        "tickColor": "#3a3d40",
        "labelColor": VALD_WHITE,
        "titleColor": VALD_WHITE,
        "labelFont": "sans-serif",
        "titleFont": "sans-serif",
    })
    config["axisX"] = {**config.get("axisX", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    config["axisY"] = {**config.get("axisY", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    # Radar chart axes (theta/radius use axisAngle/axisRadial in Vega-Lite)
    config["axisRadial"] = {**config.get("axisRadial", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE, "gridColor": "#3a3d40"}
    config["axisAngle"] = {**config.get("axisAngle", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    # Positional axis variants
    config["axisLeft"] = {**config.get("axisLeft", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    config["axisRight"] = {**config.get("axisRight", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    config["axisTop"] = {**config.get("axisTop", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    config["axisBottom"] = {**config.get("axisBottom", {}), "labelColor": VALD_WHITE, "titleColor": VALD_WHITE}
    config.setdefault("legend", {}).update({
        "labelColor": VALD_WHITE,
        "titleColor": VALD_WHITE,
        "labelFont": "sans-serif",
        "titleFont": "sans-serif",
    })
    config.setdefault("title", {}).update({
        "color": VALD_WHITE,
        "font": "sans-serif",
        "anchor": "middle",
        "subtitleColor": VALD_GRAY,
        "subtitleFont": "sans-serif",
    })
    # Use VALD orange as default mark color
    config.setdefault("mark", {}).update({"color": VALD_ORANGE})
    # Force all text in charts to be light colored (normal weight for quadrant labels)
    config.setdefault("text", {}).update({
        "color": VALD_WHITE,
        "font": "sans-serif",
        "fontWeight": "normal",
        "fontSize": 11,
    })
    config.setdefault("header", {}).update({
        "labelColor": VALD_WHITE,
        "titleColor": VALD_WHITE,
        "labelFont": "sans-serif",
        "titleFont": "sans-serif",
    })
    config.setdefault("range", {}).setdefault(
        "category", [VALD_ORANGE, "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD"]
    )

    # Recursively force white axis colors on all encoding channels in nested specs.
    # Also force text marks to white with normal font weight.
    def _force_encoding_axis_colors(obj: dict[str, Any] | Any) -> None:
        if not isinstance(obj, dict):
            return
        if "encoding" in obj and isinstance(obj["encoding"], dict):
            for ch, enc in obj["encoding"].items():
                if isinstance(enc, dict) and (enc.get("field") or enc.get("aggregate") or enc.get("axis")):
                    enc.setdefault("axis", {})
                    enc["axis"]["labelColor"] = VALD_WHITE
                    enc["axis"]["titleColor"] = VALD_WHITE
        # Force text mark layers to white + normal weight
        mark = obj.get("mark")
        if mark == "text" or (isinstance(mark, dict) and mark.get("type") == "text"):
            if isinstance(mark, dict):
                mark.setdefault("color", VALD_WHITE)
                mark.setdefault("fontWeight", "normal")
                mark.setdefault("fontSize", 11)
            obj.setdefault("encoding", {}).setdefault("color", {"value": VALD_WHITE})
        # Recurse into layer, concat, hconcat, vconcat, spec
        for key in ("layer", "concat", "hconcat", "vconcat"):
            if key in obj and isinstance(obj[key], list):
                for sub in obj[key]:
                    _force_encoding_axis_colors(sub)
        if "spec" in obj and isinstance(obj["spec"], dict):
            _force_encoding_axis_colors(obj["spec"])

    _force_encoding_axis_colors(spec)

    # Render chart via components.html() with inlined Vega JS — CSP-compliant for SiS
    spec_json = json.dumps(spec, sort_keys=True)
    html = _build_chart_html(spec_json)
    components.html(html, height=height + _IFRAME_EXTRA_PX)
