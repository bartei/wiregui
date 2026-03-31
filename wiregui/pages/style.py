"""Shared UI styling — font, theme, global CSS."""

from nicegui import ui


def apply_style():
    """Add Manrope font and global CSS overrides. Call once per page."""
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@200..800&display=swap" rel="stylesheet">'
    )
    ui.add_css("""
        body, input, button, select, textarea {
            font-family: 'Manrope', sans-serif !important;
        }
        code, .font-mono, .q-table__container .monospace {
            font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        }
    """)