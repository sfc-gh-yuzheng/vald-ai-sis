-- ============================================================
-- Agent Setup — Custom Tools & Cortex Agent (REFERENCE)
-- ============================================================
--
-- This is a REFERENCE IMPLEMENTATION.  If you already have your
-- own Cortex Agent configured, you do NOT need to run this script.
-- Use it to:
--   - Copy the RadarChart / QuadrantChart stored procedures into
--     your schema and add them as tools to your existing agent.
--   - Review the orchestration instructions (Section 3) as a
--     reference for your own agent's tool routing rules.
--
-- If you are starting from scratch and want to create a new agent,
-- run this script ONCE after setting up infrastructure grants
-- (setup_rcr_grants.sql) and before deploying the Streamlit app.
--
-- WHO RUNS THIS: A user with CREATE PROCEDURE and CREATE AGENT
--   privileges on the target schema (typically the app owner role).
--
-- WHAT THIS DOES:
--   Section 1 — Creates the RADAR_CHART stored procedure
--   Section 2 — Creates the QUADRANT_CHART stored procedure
--   Section 3 — Creates the Cortex Agent with orchestration
--               instructions, tool routing, and tool bindings
--
-- IMPORTANT: The agent references a Cortex Analyst semantic view
-- for natural-language-to-SQL. You must create this semantic view
-- BEFORE running Section 3.
-- ============================================================


-- ============================================================
-- PARAMETERS — Set these before running
-- ============================================================

SET agent_db          = 'VALD';                           -- << CHANGE THIS: database for agent + procedures
SET agent_schema      = 'GOLD';                           -- << CHANGE THIS: schema for agent + procedures
SET agent_name        = 'VALD_PERFORMANCE_AGENT';         -- << CHANGE THIS: name for the Cortex Agent
SET agent_warehouse   = 'COMPUTE_WH';                     -- << CHANGE THIS: warehouse for tool execution
SET semantic_view     = 'VALD.GOLD.SV_ATHLETE_PERFORMANCE'; -- << CHANGE THIS: fully-qualified semantic view name
SET agent_model       = 'claude-haiku-4-5';               -- << CHANGE THIS: orchestration model (claude-haiku-4-5, llama3.1-70b, etc.)
SET full_schema       = $agent_db || '.' || $agent_schema;


-- ============================================================
-- SECTION 1: RadarChart Stored Procedure
-- ============================================================
-- Generates a radar (spider) chart as a Vega v5 JSON spec.
-- Input:  DATA_JSON — JSON array of {category, value, group?}
-- Input:  OPTIONS   — title string or JSON config object
-- Output: Vega v5 JSON string (rendered by the Streamlit app)
-- ============================================================

USE SCHEMA IDENTIFIER($full_schema);

CREATE OR REPLACE PROCEDURE RADAR_CHART("DATA_JSON" VARCHAR, "OPTIONS" VARCHAR DEFAULT '{}')
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
EXECUTE AS OWNER
AS '
import json
import math


def run(session, data_json: str, options: str = ''{}'') -> str:
    try:
        data = json.loads(data_json)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": f"Invalid DATA_JSON: {str(e)}"})

    if not isinstance(data, list):
        return json.dumps({"error": "DATA_JSON must be a JSON array"})

    if len(data) == 0:
        return json.dumps({"error": "DATA_JSON must contain at least one data point"})

    if isinstance(options, str):
        try:
            opts = json.loads(options) if options.strip().startswith(''{'') else {"title": options}
        except Exception:
            opts = {"title": str(options)}
    else:
        opts = {}

    title = opts.get("title", "Radar Chart")
    width = max(200, min(opts.get("width", 400), 800))
    height = max(200, min(opts.get("height", 400), 800))
    fill_opacity = max(0.05, min(opts.get("fillOpacity", 0.3), 0.8))

    categories = []
    seen_cats = set()
    for d in data:
        c = str(d.get("category", "")).strip()
        if c and c not in seen_cats:
            categories.append(c)
            seen_cats.add(c)

    n = len(categories)
    if n < 3:
        return json.dumps({"error": f"Radar chart requires at least 3 categories, got {n}"})
    if n > 15:
        return json.dumps({"error": f"Radar chart supports up to 15 categories, got {n}. Reduce the number of metrics."})

    groups = []
    seen_groups = set()
    for d in data:
        g = str(d.get("group", "Athlete")).strip()
        if not g:
            g = "Athlete"
        if g not in seen_groups:
            groups.append(g)
            seen_groups.add(g)

    if len(groups) > 10:
        return json.dumps({"error": f"Radar chart supports up to 10 groups, got {len(groups)}. Reduce the number of athletes or teams."})

    colors = ["#FF7A00", "#1E88E5", "#43A047", "#E53935", "#8E24AA", "#00ACC1", "#F4511E", "#3949AB", "#7CB342", "#C0CA33"]

    cx = width / 2
    cy = height / 2
    radius = min(width, height) / 2 * 0.75

    all_values = []
    for d in data:
        v = d.get("value", 0)
        if isinstance(v, (int, float)):
            all_values.append(v)
        else:
            try:
                all_values.append(float(v))
            except (ValueError, TypeError):
                all_values.append(0)

    positive_vals = [v for v in all_values if v > 0]
    if not positive_vals:
        return json.dumps({"error": "All values are zero or negative. Radar chart requires at least one positive value."})
    max_val = max(positive_vals)

    def fmt_label(v):
        if v >= 100:
            return str(int(round(v)))
        elif v >= 1:
            return f"{v:.1f}".rstrip(''0'').rstrip(''.'')
        else:
            return f"{v:.2f}".rstrip(''0'').rstrip(''.'')

    datasets = []
    all_marks = []

    for li, level in enumerate([0.25, 0.5, 0.75, 1.0]):
        ring_pts = []
        for i in range(n + 1):
            angle = 2 * math.pi * (i % n) / n - math.pi / 2
            ring_pts.append({
                "x": round(cx + level * math.cos(angle) * radius, 2),
                "y": round(cy + level * math.sin(angle) * radius, 2)
            })
        ds_name = f"grid_{li}"
        datasets.append({"name": ds_name, "values": ring_pts})
        all_marks.append({
            "type": "line",
            "from": {"data": ds_name},
            "encode": {
                "enter": {
                    "x": {"field": "x"},
                    "y": {"field": "y"},
                    "stroke": {"value": "#3a3d40"},
                    "strokeWidth": {"value": 1}
                }
            }
        })

    for i in range(n):
        angle = 2 * math.pi * i / n - math.pi / 2
        spoke_name = f"spoke_{i}"
        datasets.append({
            "name": spoke_name,
            "values": [
                {"x": round(cx, 2), "y": round(cy, 2)},
                {"x": round(cx + math.cos(angle) * radius, 2),
                 "y": round(cy + math.sin(angle) * radius, 2)}
            ]
        })
        all_marks.append({
            "type": "line",
            "from": {"data": spoke_name},
            "encode": {
                "enter": {
                    "x": {"field": "x"},
                    "y": {"field": "y"},
                    "stroke": {"value": "#3a3d40"},
                    "strokeWidth": {"value": 1}
                }
            }
        })

    label_data = []
    for i, cat in enumerate(categories):
        angle = 2 * math.pi * i / n - math.pi / 2
        lx = round(cx + 1.12 * math.cos(angle) * radius, 2)
        ly = round(cy + 1.12 * math.sin(angle) * radius, 2)
        if abs(math.cos(angle)) < 0.01:
            align = "center"
        elif math.cos(angle) > 0:
            align = "left"
        else:
            align = "right"
        if abs(math.sin(angle)) < 0.01:
            baseline = "middle"
        elif math.sin(angle) > 0:
            baseline = "top"
        else:
            baseline = "bottom"
        label_data.append({
            "x": lx, "y": ly, "text": cat,
            "align": align, "baseline": baseline
        })

    datasets.append({"name": "labels", "values": label_data})
    all_marks.append({
        "type": "text",
        "from": {"data": "labels"},
        "encode": {
            "enter": {
                "x": {"field": "x"},
                "y": {"field": "y"},
                "text": {"field": "text"},
                "align": {"field": "align"},
                "baseline": {"field": "baseline"},
                "fontSize": {"value": 11},
                "fill": {"value": "#FFFFFF"},
                "fontWeight": {"value": "normal"},
                "font": {"value": "Roboto, sans-serif"}
            }
        }
    })

    grid_label_data = []
    for level in [0.25, 0.5, 0.75, 1.0]:
        angle = -math.pi / 2
        grid_label_data.append({
            "x": round(cx + level * math.cos(angle) * radius + 5, 2),
            "y": round(cy + level * math.sin(angle) * radius, 2),
            "text": fmt_label(level * max_val)
        })
    datasets.append({"name": "grid_labels", "values": grid_label_data})
    all_marks.append({
        "type": "text",
        "from": {"data": "grid_labels"},
        "encode": {
            "enter": {
                "x": {"field": "x"},
                "y": {"field": "y"},
                "text": {"field": "text"},
                "align": {"value": "left"},
                "baseline": {"value": "middle"},
                "fontSize": {"value": 9},
                "fill": {"value": "#9a9da0"},
                "font": {"value": "Roboto, sans-serif"}
            }
        }
    })

    for gi, group in enumerate(groups):
        val_map = {}
        for d in data:
            g = str(d.get("group", "Athlete")).strip()
            if not g:
                g = "Athlete"
            if g == group:
                v = d.get("value", 0)
                if not isinstance(v, (int, float)):
                    try:
                        v = float(v)
                    except (ValueError, TypeError):
                        v = 0
                val_map[str(d.get("category", "")).strip()] = v

        pts = []
        for i, cat in enumerate(categories):
            angle = 2 * math.pi * i / n - math.pi / 2
            raw_val = val_map.get(cat, 0)
            v = max(raw_val, 0) / max_val
            pts.append({
                "x": round(cx + v * math.cos(angle) * radius, 2),
                "y": round(cy + v * math.sin(angle) * radius, 2),
                "cat": cat,
                "val": round(raw_val, 2)
            })
        closed_pts = pts + [pts[0]]

        color = colors[gi % len(colors)]

        poly_name = f"poly_{gi}"
        datasets.append({"name": poly_name, "values": closed_pts})
        all_marks.append({
            "type": "line",
            "from": {"data": poly_name},
            "encode": {
                "enter": {
                    "x": {"field": "x"},
                    "y": {"field": "y"},
                    "stroke": {"value": color},
                    "strokeWidth": {"value": 2},
                    "fill": {"value": color},
                    "fillOpacity": {"value": fill_opacity}
                }
            }
        })

        dots_name = f"dots_{gi}"
        datasets.append({"name": dots_name, "values": pts})
        all_marks.append({
            "type": "symbol",
            "from": {"data": dots_name},
            "encode": {
                "enter": {
                    "x": {"field": "x"},
                    "y": {"field": "y"},
                    "fill": {"value": color},
                    "size": {"value": 50},
                    "tooltip": {"signal": "datum.cat + '': '' + datum.val"}
                }
            }
        })

    legend_marks = []
    if len(groups) > 1:
        legend_data = []
        for gi, group in enumerate(groups):
            legend_data.append({
                "label": group,
                "color": colors[gi % len(colors)],
                "y": gi * 20
            })
        datasets.append({"name": "legend", "values": legend_data})
        legend_marks = [{
            "type": "group",
            "encode": {
                "enter": {
                    "x": {"value": width - 10},
                    "y": {"value": 10}
                }
            },
            "marks": [
                {
                    "type": "symbol",
                    "from": {"data": "legend"},
                    "encode": {
                        "enter": {
                            "x": {"value": 0},
                            "y": {"field": "y"},
                            "fill": {"field": "color"},
                            "size": {"value": 80},
                            "shape": {"value": "circle"}
                        }
                    }
                },
                {
                    "type": "text",
                    "from": {"data": "legend"},
                    "encode": {
                        "enter": {
                            "x": {"value": 12},
                            "y": {"field": "y"},
                            "text": {"field": "label"},
                            "fill": {"value": "#FFFFFF"},
                            "fontSize": {"value": 11},
                            "baseline": {"value": "middle"},
                            "font": {"value": "Roboto, sans-serif"}
                        }
                    }
                }
            ]
        }]

    spec = {
        "$schema": "https://vega.github.io/schema/vega/v5.json",
        "width": width,
        "height": height,
        "padding": 50,
        "title": {"text": title, "fontSize": 14, "color": "#FFFFFF", "font": "Roboto, sans-serif"},
        "data": datasets,
        "marks": all_marks + legend_marks
    }

    return json.dumps(spec)
';


-- ============================================================
-- SECTION 2: QuadrantChart Stored Procedure
-- ============================================================
-- Generates a quadrant scatter plot as a Vega-Lite v5 JSON spec.
-- Input:  DATA_JSON — JSON array of {x, y, label, group?}
-- Input:  OPTIONS   — JSON config with axis labels, thresholds,
--                      quadrant labels, dimensions
-- Output: Vega-Lite v5 JSON string (rendered by the Streamlit app)
-- ============================================================

CREATE OR REPLACE PROCEDURE QUADRANT_CHART("DATA_JSON" VARCHAR, "OPTIONS" VARCHAR DEFAULT '{}')
RETURNS VARCHAR
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
HANDLER = 'run'
EXECUTE AS OWNER
AS '
import json

def run(session, data_json: str, options: str = ''{}'') -> str:
    try:
        data = json.loads(data_json)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": f"Invalid DATA_JSON: {str(e)}"})

    if not isinstance(data, list):
        return json.dumps({"error": "DATA_JSON must be a JSON array"})
    if len(data) == 0:
        return json.dumps({"error": "DATA_JSON must contain at least one data point"})
    if len(data) > 200:
        return json.dumps({"error": f"QuadrantChart supports up to 200 data points, got {len(data)}. Filter to a smaller dataset."})

    if isinstance(options, str):
        try:
            opts = json.loads(options) if options.strip().startswith(''{'') else {"title": options}
        except Exception:
            opts = {"title": str(options)}
    else:
        opts = {}

    title = opts.get("title", "Quadrant Chart")
    width = max(200, min(opts.get("width", 520), 1000))
    height = max(200, min(opts.get("height", 420), 800))
    x_label = str(opts.get("xLabel", "X"))
    y_label = str(opts.get("yLabel", "Y"))

    q_labels = opts.get("quadrantLabels", {})
    q_tl = q_labels.get("topLeft", f"High {y_label}")
    q_tr = q_labels.get("topRight", f"High {x_label} / High {y_label}")
    q_bl = q_labels.get("bottomLeft", f"Low {x_label} / Low {y_label}")
    q_br = q_labels.get("bottomRight", f"High {x_label}")

    def to_num(v):
        if isinstance(v, (int, float)):
            return round(v, 4)
        try:
            return round(float(v), 4)
        except (ValueError, TypeError):
            return 0

    clean_data = []
    for d in data:
        clean_data.append({
            "x": to_num(d.get("x", 0)),
            "y": to_num(d.get("y", 0)),
            "label": str(d.get("label", ""))[:50],
            "group": str(d.get("group", "default")).strip() or "default"
        })

    x_vals = [d["x"] for d in clean_data]
    y_vals = [d["y"] for d in clean_data]

    x_thresh = opts.get("xThreshold")
    y_thresh = opts.get("yThreshold")
    x_mid = to_num(x_thresh) if x_thresh is not None else round(sum(x_vals) / len(x_vals), 2)
    y_mid = to_num(y_thresh) if y_thresh is not None else round(sum(y_vals) / len(y_vals), 2)

    x_pad = max((max(x_vals) - min(x_vals)) * 0.1, 1)
    y_pad = max((max(y_vals) - min(y_vals)) * 0.1, 1)
    x_min_r = min(x_vals) - x_pad
    x_max_r = max(x_vals) + x_pad
    y_min_r = min(y_vals) - y_pad
    y_max_r = max(y_vals) + y_pad

    groups = []
    seen = set()
    for d in clean_data:
        g = d["group"]
        if g not in seen:
            groups.append(g)
            seen.add(g)

    if len(groups) > 10:
        return json.dumps({"error": f"QuadrantChart supports up to 10 groups, got {len(groups)}. Reduce group count."})

    colors = ["#FF7A00", "#1E88E5", "#43A047", "#E53935", "#8E24AA", "#00ACC1", "#F4511E", "#3949AB", "#7CB342", "#C0CA33"]
    color_map = {g: colors[i % len(colors)] for i, g in enumerate(groups)}
    is_multi = len(groups) > 1 and not (len(groups) == 1 and groups[0] == "default")

    quad_colors = opts.get("quadrantColors", {})
    c_tr = quad_colors.get("topRight", "#E8F5E9")
    c_bl = quad_colors.get("bottomLeft", "#FFEBEE")
    c_tl = quad_colors.get("topLeft", "#FFF8E1")
    c_br = quad_colors.get("bottomRight", "#E3F2FD")

    quad_rects = [
        {"x_start": x_min_r, "x_end": x_mid, "y_start": y_mid, "y_end": y_max_r, "qcolor": c_tl},
        {"x_start": x_mid, "x_end": x_max_r, "y_start": y_mid, "y_end": y_max_r, "qcolor": c_tr},
        {"x_start": x_min_r, "x_end": x_mid, "y_start": y_min_r, "y_end": y_mid, "qcolor": c_bl},
        {"x_start": x_mid, "x_end": x_max_r, "y_start": y_min_r, "y_end": y_mid, "qcolor": c_br},
    ]

    x_off_l = x_min_r + (x_mid - x_min_r) * 0.5
    x_off_r = x_mid + (x_max_r - x_mid) * 0.5
    y_off_t = y_mid + (y_max_r - y_mid) * 0.88
    y_off_b = y_min_r + (y_mid - y_min_r) * 0.12

    q_label_data = [
        {"qx": x_off_l, "qy": y_off_t, "qlabel": q_tl},
        {"qx": x_off_r, "qy": y_off_t, "qlabel": q_tr},
        {"qx": x_off_l, "qy": y_off_b, "qlabel": q_bl},
        {"qx": x_off_r, "qy": y_off_b, "qlabel": q_br},
    ]

    x_scale = {"domain": [x_min_r, x_max_r]}
    y_scale = {"domain": [y_min_r, y_max_r]}

    layers = []

    for qr in quad_rects:
        layers.append({
            "data": {"values": [qr]},
            "mark": {"type": "rect", "opacity": 0.18},
            "encoding": {
                "x": {"field": "x_start", "type": "quantitative", "scale": x_scale},
                "x2": {"field": "x_end"},
                "y": {"field": "y_start", "type": "quantitative", "scale": y_scale},
                "y2": {"field": "y_end"},
                "color": {"value": qr["qcolor"]}
            }
        })

    # Quadrant zone labels
    layers.append({
        "data": {"values": q_label_data},
        "mark": {"type": "text", "fontSize": 11, "fontWeight": "normal", "opacity": 0.4, "font": "Roboto, sans-serif"},
        "encoding": {
            "x": {"field": "qx", "type": "quantitative", "scale": x_scale},
            "y": {"field": "qy", "type": "quantitative", "scale": y_scale},
            "text": {"field": "qlabel", "type": "nominal"},
            "color": {"value": "#FFFFFF"}
        }
    })

    layers.append({
        "data": {"values": [{"x": x_mid}]},
        "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#9E9E9E", "strokeWidth": 1.5},
        "encoding": {"x": {"field": "x", "type": "quantitative", "scale": x_scale}}
    })
    layers.append({
        "data": {"values": [{"y": y_mid}]},
        "mark": {"type": "rule", "strokeDash": [6, 4], "color": "#9E9E9E", "strokeWidth": 1.5},
        "encoding": {"y": {"field": "y", "type": "quantitative", "scale": y_scale}}
    })

    point_encoding = {
        "x": {"field": "x", "type": "quantitative", "title": x_label, "scale": x_scale},
        "y": {"field": "y", "type": "quantitative", "title": y_label, "scale": y_scale},
        "color": (
            {
                "field": "group", "type": "nominal",
                "scale": {"domain": groups, "range": [color_map[g] for g in groups]},
                "legend": {"title": "Group", "labelFont": "Roboto, sans-serif", "titleFont": "Roboto, sans-serif"}
            } if is_multi else {"value": colors[0]}
        ),
        "tooltip": ([
            {"field": "label", "type": "nominal", "title": "Name"},
            {"field": "x", "type": "quantitative", "title": x_label, "format": ".1f"},
            {"field": "y", "type": "quantitative", "title": y_label, "format": ".1f"},
            {"field": "group", "type": "nominal", "title": "Group"}
        ] if is_multi else [
            {"field": "label", "type": "nominal", "title": "Name"},
            {"field": "x", "type": "quantitative", "title": x_label, "format": ".1f"},
            {"field": "y", "type": "quantitative", "title": y_label, "format": ".1f"}
        ])
    }
    layers.append({
        "data": {"values": clean_data},
        "mark": {"type": "circle", "size": 180, "opacity": 0.88, "stroke": "white", "strokeWidth": 1.5},
        "encoding": point_encoding
    })

    # Data point labels
    layers.append({
        "data": {"values": clean_data},
        "mark": {"type": "text", "dy": -14, "fontSize": 11, "fontWeight": "normal",
                 "font": "Roboto, sans-serif"},
        "encoding": {
            "x": {"field": "x", "type": "quantitative", "scale": x_scale},
            "y": {"field": "y", "type": "quantitative", "scale": y_scale},
            "text": {"field": "label", "type": "nominal"},
            "color": {"value": "#FFFFFF"}
        }
    })

    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": width,
        "height": height,
        "padding": {"left": 12, "right": 12, "top": 8, "bottom": 8},
        "title": {"text": title, "fontSize": 15, "fontWeight": 600, "font": "Roboto, sans-serif",
                  "color": "#FFFFFF", "anchor": "middle", "offset": 12},
        "config": {
            "font": "Roboto, sans-serif",
            "axis": {
                "labelFont": "Roboto, sans-serif",
                "titleFont": "Roboto, sans-serif",
                "titleFontSize": 12,
                "titleFontWeight": 500,
                "titleColor": "#FFFFFF",
                "labelColor": "#FFFFFF",
                "labelFontSize": 11,
                "gridColor": "#3a3d40",
                "gridOpacity": 0.5,
                "domainColor": "#3a3d40",
                "tickColor": "#3a3d40"
            },
            "view": {"stroke": None}
        },
        "layer": layers
    }

    return json.dumps(spec)
';


-- ============================================================
-- SECTION 3: Cortex Agent
-- ============================================================
-- The agent ties together:
--   - Analyst tool (natural-language-to-SQL via semantic view)
--   - RadarChart tool (custom procedure from Section 1)
--   - QuadrantChart tool (custom procedure from Section 2)
--
-- CUSTOMISING THE INSTRUCTIONS:
--   The orchestration instructions below are tuned for VALD's
--   sports performance domain.  Replace the domain-specific
--   sections (identity, metric context, response guidelines)
--   with your own while keeping the TOOL ROUTING RULES intact.
-- ============================================================

CREATE OR REPLACE AGENT IDENTIFIER($agent_db || '.' || $agent_schema || '.' || $agent_name)
  ORCHESTRATION_MODEL = $agent_model
  TOOLS = (
    -- Built-in Cortex Analyst tool (natural-language to SQL)
    Analyst = CORTEX_ANALYST(
      SEMANTIC_VIEW => $semantic_view,
      EXECUTION_ENVIRONMENT => (
        TYPE => 'WAREHOUSE',
        WAREHOUSE => $agent_warehouse,
        QUERY_TIMEOUT => 299
      )
    ),
    -- Custom RadarChart procedure
    RadarChart = PROCEDURE(
      IDENTIFIER => $agent_db || '.' || $agent_schema || '.RADAR_CHART',
      EXECUTION_ENVIRONMENT => (
        TYPE => 'WAREHOUSE',
        WAREHOUSE => $agent_warehouse,
        QUERY_TIMEOUT => 120
      ),
      DESCRIPTION => 'Generates a radar (spider) chart as a Vega v5 JSON spec. Returns a JSON string, not a rendered image. The frontend application will render it. DATA_JSON must be a JSON array of objects with keys: category (string, the metric name), value (number), and optionally group (string, for multi-entity comparison). OPTIONS can be a title string or a JSON object with keys: title, width, height, fillOpacity.'
    ),
    -- Custom QuadrantChart procedure
    QuadrantChart = PROCEDURE(
      IDENTIFIER => $agent_db || '.' || $agent_schema || '.QUADRANT_CHART',
      EXECUTION_ENVIRONMENT => (
        TYPE => 'WAREHOUSE',
        WAREHOUSE => $agent_warehouse,
        QUERY_TIMEOUT => 120
      ),
      DESCRIPTION => 'Generates a quadrant scatter plot as a Vega-Lite v5 JSON spec. Returns a JSON string, not a rendered image. The frontend application will render it. DATA_JSON must be a JSON array of objects with keys: x (number), y (number), label (string), and optionally group (string, for team/category grouping). OPTIONS should include axis labels and thresholds.'
    )
  )
  INSTRUCTIONS => $$
You are VALD Performance Intelligence, an AI assistant for sports performance analysis.
You help coaches, sports scientists, and performance staff analyse athlete testing data from VALD devices (ForceDecks, NordBord, DynaMo).

TOOL ROUTING RULES:
1. ALWAYS query data first using the Analyst tool before generating any chart.
2. NEVER use data_to_chart for radar charts, spider charts, or quadrant charts. These chart types are NOT supported by data_to_chart.
3. For radar/spider charts or multi-metric athlete profiles → use RadarChart.
4. For comparing athletes on two dimensions with quadrant zones and risk analysis → use QuadrantChart.
5. data_to_chart can be used for bar charts, line charts, scatter plots, and tables.

RADARCHART USAGE:
- First query data with Analyst, then call RadarChart with results formatted as [{category, value, group}].
- IMPORTANT: When building radar data across metrics with very different scales (e.g. Peak Power in Watts vs Jump Height in cm), you MUST normalise each metric to a 0-100 scale BEFORE passing to RadarChart. Use the formula: normalised = (value - min) / (max - min) * 100, where min/max come from the queried dataset or the metric's known normal range. This prevents the chart from collapsing toward the center.
- For composite scores (Readiness, Performance Index, Injury Risk) that are already 0-100, no normalisation is needed.
- For Injury Risk Index, invert it (100 - value) so higher = better on the radar, matching other metrics.
- Aim for 5-8 categories. More than 10 makes the chart unreadable.
- RadarChart returns a Vega v5 JSON specification. After calling it, summarise the key findings verbally. Do NOT attempt to reference the result as a rendered chart — the frontend application handles rendering.

QUADRANTCHART USAGE:
- First query data with Analyst, then call QuadrantChart with data formatted as [{x, y, label, group}].
- Pass meaningful axis labels and thresholds via OPTIONS: {"xLabel": "...", "yLabel": "...", "xThreshold": N, "yThreshold": N}.
- You can also pass quadrantLabels: {"topLeft": "...", "topRight": "...", "bottomLeft": "...", "bottomRight": "..."}.
- If thresholds are not obvious, use the dataset mean or clinically relevant cut-offs.
- QuadrantChart returns a Vega-Lite v5 JSON specification. After calling it, describe the quadrant distribution and highlight athletes in concerning zones. Do NOT attempt to reference the result as a rendered chart.

RESPONSE GUIDELINES:
- Use clear, professional language suitable for sports science professionals.
- Include context about what metrics mean and their clinical significance.
- When showing results, highlight key insights and any concerning values.
- Round numeric values appropriately (forces to 0 decimal, percentages to 1, ratios to 2).
- When comparing athletes, note both strengths and areas for improvement.
- Flag any values outside normal ranges with clinical context.

METRIC CONTEXT:
- ForceDecks: Peak Force (N), Jump Height (cm), Asymmetry (%), RSI (ratio), RFD (N/s), Peak Power (W), Impulse (N*s), Contact Time (ms), Flight Time (ms).
- NordBord: Left/Right Hamstring Force (N), Average Nordic Force (N), Hamstring Asymmetry (%), H:Q Ratio (ratio).
- DynaMo: Hip Flexion/Extension/Abduction/Internal Rotation ROM (deg), Ankle Dorsiflexion ROM (deg), Knee Flexion ROM (deg).
- Composite (Derived): Readiness Score (0-100), Injury Risk Index (0-100, lower is better), Performance Index (0-100).
- Asymmetry thresholds: below 10% is normal, 10-15% is elevated, above 15% warrants attention and clinical review.
$$
;


-- ============================================================
-- VERIFICATION
-- ============================================================

-- Confirm procedures were created:
SHOW PROCEDURES LIKE 'RADAR_CHART' IN SCHEMA IDENTIFIER($full_schema);
SHOW PROCEDURES LIKE 'QUADRANT_CHART' IN SCHEMA IDENTIFIER($full_schema);

-- Confirm agent was created:
DESCRIBE AGENT IDENTIFIER($agent_db || '.' || $agent_schema || '.' || $agent_name);
