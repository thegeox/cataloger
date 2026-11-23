"""Starter templates offered in the UI."""

PRESETS = [
    {
        "name": "Ficha de producto (cuadrada)",
        "definition": {
            "width": 1080,
            "height": 1080,
            "background": "#ffffff",
            "elements": [
                {"id": "foto", "type": "image", "x": 60, "y": 60, "width": 960, "height": 720, "fit": "contain"},
                {"id": "banda", "type": "rect", "x": 0, "y": 820, "width": 1080, "height": 260, "fill": "#1f2937"},
                {"id": "titulo", "type": "text", "x": 60, "y": 845, "width": 700, "height": 110,
                 "text": "{{_stem}}", "font_size": 56, "bold": True, "color": "#ffffff", "valign": "middle"},
                {"id": "detalle", "type": "text", "x": 60, "y": 960, "width": 700, "height": 90,
                 "text": "Archivo: {{_name}}", "font_size": 32, "color": "#d1d5db"},
                {"id": "precio", "type": "text", "x": 760, "y": 845, "width": 260, "height": 205,
                 "text": "#{{_index}}", "font_size": 72, "bold": True, "color": "#fbbf24",
                 "align": "right", "valign": "middle"},
            ],
        },
    },
    {
        "name": "Tarjeta vertical",
        "definition": {
            "width": 1200,
            "height": 1600,
            "background": "#f5f1ea",
            "elements": [
                {"id": "foto", "type": "image", "x": 80, "y": 80, "width": 1040, "height": 1040,
                 "fit": "cover", "radius": 24},
                {"id": "titulo", "type": "text", "x": 80, "y": 1160, "width": 1040, "height": 140,
                 "text": "{{_stem|upper}}", "font_family": "serif", "font_size": 72, "bold": True,
                 "color": "#2b2118"},
                {"id": "texto", "type": "text", "x": 80, "y": 1310, "width": 1040, "height": 210,
                 "text": "Edita este texto e inserta campos de metadata con {{campo}}.",
                 "font_size": 40, "color": "#5b4a3a"},
            ],
        },
    },
    {
        "name": "Etiqueta horizontal",
        "definition": {
            "width": 1500,
            "height": 900,
            "background": "#ffffff",
            "elements": [
                {"id": "marco", "type": "rect", "x": 20, "y": 20, "width": 1460, "height": 860,
                 "fill": None, "stroke": "#111827", "stroke_width": 6, "radius": 20},
                {"id": "foto", "type": "image", "x": 60, "y": 60, "width": 780, "height": 780, "fit": "contain"},
                {"id": "titulo", "type": "text", "x": 880, "y": 80, "width": 560, "height": 200,
                 "text": "{{_stem}}", "font_size": 64, "bold": True},
                {"id": "texto", "type": "text", "x": 880, "y": 300, "width": 560, "height": 520,
                 "text": "{{_name}}", "font_size": 36, "color": "#374151"},
            ],
        },
    },
]
