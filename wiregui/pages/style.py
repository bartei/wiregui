"""Shared UI styling — font, theme, global CSS."""

from nicegui import ui

# Logo palette
_NAVY = "#0E2747"
_BLUE = "#3598C3"
_TEAL = "#5AA6B9"
_TEAL_LIGHT = "#7AC7D6"
_MID_BLUE = "#325F7B"


def apply_style():
    """Add Manrope font, logo-based color theme, and global CSS overrides. Call once per page."""
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200..800&display=swap" rel="stylesheet">'
    )
    ui.add_css(f"""
        body, input, button, select, textarea {{
            font-family: 'Manrope', sans-serif !important;
        }}
        code, .font-mono, .q-table__container .monospace {{
            font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        }}

        /* ---- Light theme colors ---- */
        :root {{
            --q-primary: {_BLUE};
            --q-secondary: {_TEAL};
            --q-accent: {_TEAL_LIGHT};
            --q-dark: {_NAVY};
            --q-positive: #21BA45;
            --q-negative: #C10015;
            --q-info: {_MID_BLUE};
            --q-warning: #F2C037;
        }}

        /* Header bar */
        .q-header {{
            background: linear-gradient(135deg, {_NAVY} 0%, {_MID_BLUE} 100%) !important;
        }}

        /* Left drawer */
        .q-drawer {{
            border-right-color: {_TEAL}33 !important;
        }}

        /* ---- Dark theme overrides ---- */
        body.body--dark {{
            --q-primary: {_TEAL};
            --q-secondary: {_BLUE};
            --q-accent: {_TEAL_LIGHT};
            --q-dark: {_NAVY};
            --q-info: {_TEAL_LIGHT};
        }}

        body.body--dark .q-header {{
            background: linear-gradient(135deg, {_NAVY} 0%, #1a3a5c 100%) !important;
        }}

        body.body--dark .q-drawer {{
            border-right-color: {_MID_BLUE}44 !important;
        }}
    """)