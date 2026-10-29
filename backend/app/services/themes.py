"""Website style presets for tenant sites (Acuity-style themes).

Each preset defines an accent colour, light/dark mode and an optional font.
Businesses pick a preset (theme_style) or a fully custom colour + dark mode
combination (theme_style = 'custom'). Fonts are stored as keys into
FONT_OPTIONS so owners can also pick a font independently of the preset.
"""

THEME_STYLES: dict = {
    "rose":     {"label": "Rose",     "accent": "#ec4899", "dark": False, "font": "default", "pattern": "🌸"},
    "midnight": {"label": "Midnight", "accent": "#d4a017", "dark": True,  "font": "georgia", "pattern": "🌙"},
    "ocean":    {"label": "Ocean",    "accent": "#0ea5e9", "dark": False, "font": "default", "pattern": "🌊"},
    "forest":   {"label": "Forest",   "accent": "#10b981", "dark": False, "font": "default", "pattern": "🍃"},
    "sunset":   {"label": "Sunset",   "accent": "#f97316", "dark": False, "font": "default", "pattern": "🌅"},
    "violet":   {"label": "Violet",   "accent": "#8b5cf6", "dark": True,  "font": "default", "pattern": "✨"},
    "mono":     {"label": "Mono",     "accent": "#111827", "dark": False, "font": "courier", "pattern": "▦"},
}

# Font choices shown in the app and portal. Keys are stored in theme_font.
FONT_OPTIONS: dict = {
    "default":   {"label": "Default (system)", "stack": ""},
    "georgia":   {"label": "Georgia",          "stack": "Georgia, 'Times New Roman', serif"},
    "times":     {"label": "Times New Roman",  "stack": "'Times New Roman', Times, serif"},
    "arial":     {"label": "Arial",            "stack": "Arial, Helvetica, sans-serif"},
    "helvetica": {"label": "Helvetica",        "stack": "Helvetica, Arial, sans-serif"},
    "verdana":   {"label": "Verdana",          "stack": "Verdana, Geneva, sans-serif"},
    "tahoma":    {"label": "Tahoma",           "stack": "Tahoma, Geneva, sans-serif"},
    "trebuchet": {"label": "Trebuchet MS",     "stack": "'Trebuchet MS', 'Segoe UI', sans-serif"},
    "courier":   {"label": "Courier New",      "stack": "'Courier New', Courier, monospace"},
    "palatino":  {"label": "Palatino",         "stack": "Palatino, 'Palatino Linotype', serif"},
}


def resolve_font_stack(value: str) -> str:
    """Turn a stored theme_font value into a CSS font stack.

    New values are keys into FONT_OPTIONS; older rows may already contain a
    full CSS stack, which is returned unchanged.
    """
    if not value:
        return ""
    if value in FONT_OPTIONS:
        return FONT_OPTIONS[value]["stack"]
    return value
