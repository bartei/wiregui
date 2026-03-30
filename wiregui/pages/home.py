from nicegui import app, ui


@ui.page("/")
def home_page():
    if not app.storage.user.get("authenticated"):
        return ui.navigate.to("/login")
    # Redirect to devices as the main landing page
    return ui.navigate.to("/devices")
