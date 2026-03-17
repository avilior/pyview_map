from __future__ import annotations

import html
import os

from markupsafe import Markup
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route
from starlette.staticfiles import StaticFiles
from pyview import PyView, defaultRootTemplate
from pyview.vendor.ibis.loaders import FileReloader

from debate_bff.views.chat.chat_view import ChatLiveView
from debate_bff import transcript_store

# ---------------------------------------------------------------------------
# PyView application
# ---------------------------------------------------------------------------

app = PyView()

# Root template — Tailwind CSS via CDN for rapid prototyping
css = Markup("""<script src="https://cdn.tailwindcss.com"></script>
<script>
window.Hooks = window.Hooks || {};
window.Hooks.ChatScroll = {
  mounted() { this._scroll(); },
  updated() { this._scroll(); },
  _scroll() {
    var last = this.el.querySelector('[data-msg]:last-child');
    if (last) { last.scrollIntoView({behavior: 'smooth', block: 'start'}); }
    else { this.el.scrollTop = this.el.scrollHeight; }
  }
};
</script>""")
app.rootTemplate = defaultRootTemplate(css=css)

# Serve static files (PyView JS client + our own assets)
app.mount(
    "/static",
    StaticFiles(
        packages=[("pyview", "static")],
    ),
    name="static",
)

# Hot-reload templates in development
_views_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "views")
FileReloader(_views_dir)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

app.add_live_view("/", ChatLiveView)


async def _transcript_view(request) -> Response:
    """Serve a stored transcript as a styled HTML page."""
    debate_id = request.path_params["debate_id"]
    entry = transcript_store.transcripts.get(debate_id)
    if entry is None:
        return HTMLResponse("<h1>Transcript not found</h1>", status_code=404)
    content, fmt = entry
    if fmt == "html":
        body = f'<div class="prose max-w-none">{content}</div>'
    else:
        escaped = html.escape(content)
        body = f'<pre class="whitespace-pre-wrap font-sans text-gray-800 leading-relaxed">{escaped}</pre>'
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Transcript</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 p-8">
    <div class="max-w-3xl mx-auto bg-white rounded-xl shadow p-8">
        {body}
    </div>
</body>
</html>"""
    return HTMLResponse(page)


app.routes.append(Route("/transcript/{debate_id}", _transcript_view, methods=["GET"]))
