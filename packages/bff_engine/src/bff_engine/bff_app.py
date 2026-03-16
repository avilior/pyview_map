"""PyView app factory — shared CSS, static file mounting, root template."""

from pyview import PyView, defaultRootTemplate
from starlette.staticfiles import StaticFiles
from markupsafe import Markup

_SHARED_CSS = """
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    theme: {
      extend: {
        colors: {
          'pyview-pink': {
            50: '#fdf2f8',
            100: '#fce7f3',
            200: '#fbcfe8',
            300: '#f9a8d4',
            400: '#f472b6',
            500: '#ec4899',
            600: '#db2777',
            700: '#be185d',
            800: '#9d174d',
            900: '#831843'
          }
        },
        fontFamily: {
          'sans': ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
          'display': ['Poppins', 'system-ui', '-apple-system', 'sans-serif']
        }
      }
    }
  }
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Poppins:wght@600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/nprogress@0.2.0/nprogress.css" />

<!-- Leaflet CSS + JS -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />

 <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
     integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
     crossorigin=""></script>

<script src="https://unpkg.com/@joergdietrich/leaflet.terminator@1.0.0/L.Terminator.js"></script>
<script src="https://unpkg.com/leaflet.repeatedmarkers@latest/Leaflet.RepeatedMarkers.js"></script>
"""


def create_app(
    static_packages: list[str],
    extra_head_html: str = "",
) -> PyView:
    """Create a configured PyView app.

    Args:
        static_packages: dotted package names whose ``static/`` dirs to mount
            (e.g. ``["bff_engine.dynamic_map", "bff_engine.dynamic_list"]``).
        extra_head_html: additional ``<script>``/``<link>`` tags for the ``<head>``.
    """
    app = PyView()
    packages = [("pyview", "static")] + [(pkg, "static") for pkg in static_packages]
    app.mount("/static", StaticFiles(packages=packages), name="static")
    full_css = _SHARED_CSS + extra_head_html
    app.rootTemplate = defaultRootTemplate(css=Markup(full_css))
    return app
