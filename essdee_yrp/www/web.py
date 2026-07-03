"""Context provider for the Essdee YRP custom SPA at `/web`.

Serves the Vue 3 + PrimeVue single-page app built into
`essdee_yrp/public/frontend/`. Same serving pattern as the bench's other
custom-frontend apps:

  1. Guests are redirected to /login?redirect-to=/web.
  2. The hashed Vite entry assets (essdee-<hash>.js / index-<hash>.css) are
     resolved at request time by globbing the build output, so the template
     always points at the current bundle without a rebuild step touching this
     file.
  3. The client receives `frappe.boot` (user via load_user() — carries roles +
     can_read/can_create/... used by usePermissions) and a CSRF token.

The `/web/<path:app_path>` deep links are routed here via `website_route_rules`
in hooks.py so the Vue router (history mode, base "/web") owns sub-paths.
"""

import glob
import json
import os

import frappe
import frappe.sessions  # noqa: F401  (ensures get_csrf_token is importable)

no_cache = 1

ASSET_BASE = "/assets/essdee_yrp/frontend/"


def _website_asset(field, fallback):
	"""Logo / favicon are sourced from Website Settings so an admin controls them
	without a rebuild; fall back to the bundled Essdee asset when the field is empty."""
	return frappe.db.get_single_value("Website Settings", field) or (ASSET_BASE + fallback)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/web"
		raise frappe.Redirect

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()

	context.csrf_token = csrf_token
	context.boot = get_boot()
	context.favicon = _website_asset("favicon", "favicon.png")
	context.no_cache = 1
	context.no_header = 1
	context.no_sidebar = 1
	context.no_breadcrumbs = 1

	js_file, css_file = _resolve_frontend_assets()
	context.frontend_js = js_file
	context.frontend_css = css_file

	return context


def _resolve_frontend_assets():
	"""Return (js_url, css_url) for the current hashed Vite entry files."""
	assets_dir = os.path.join(
		os.path.dirname(__file__), "..", "public", "frontend", "assets"
	)
	assets_dir = os.path.realpath(assets_dir)

	base = "/assets/essdee_yrp/frontend/assets/"
	js_file = base + "essdee.js"
	css_file = ""

	# Entry JS uses the distinct "essdee-" prefix (set in vite.config.js
	# entryFileNames) so this never accidentally matches a vendor chunk.
	js_matches = glob.glob(os.path.join(assets_dir, "essdee-*.js"))
	if js_matches:
		js_file = base + os.path.basename(js_matches[0])

	# Entry CSS is emitted as index-<hash>.css (Vite names extracted entry CSS
	# via assetFileNames [name]=index). Route-level CSS is named after its
	# component (DynamicListPage-*.css, …), so index-*.css uniquely matches the
	# global entry stylesheet.
	css_matches = glob.glob(os.path.join(assets_dir, "index-*.css"))
	if css_matches:
		css_file = base + os.path.basename(css_matches[0])

	return js_file, css_file


def get_boot():
	return {
		"site_name": frappe.local.site,
		# Realtime: the /web SPA opens its own socket.io connection to Frappe's
		# realtime server (default port 9000) for live doc/list updates. Exposed
		# here so the client builds the URL host-only (window.location.hostname +
		# this port + "/" + site_name), avoiding the :8003:9000 double-port.
		"socketio_port": frappe.conf.socketio_port or 9000,
		"app_logo": _website_asset("app_logo", "essdee-logo.png"),
		"user": json.loads(frappe.as_json(frappe.get_user().load_user())),
	}
