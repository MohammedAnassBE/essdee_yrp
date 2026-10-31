"""Context provider for the SD YRP custom SPA at `/web`.

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
import frappe.sessions
from frappe.core.doctype.navbar_settings.navbar_settings import get_app_logo

no_cache = 1


# The exact DocTypes the /web SPA exposes. CHECKLIST RULE (spec §8.1): whenever
# a routed doctype is added to the frontend, add it HERE so
# _apply_accurate_web_perms keeps correcting boot's leaky perm superset. Keep
# hooks.py `yrp_web_doctype_catalog` (base yrp's ui_config validation input) in
# the same order. The SPA gates sidebar / command palette / home visibility on
# frappe.boot.user.can_read, but Frappe's load_user()/build_permissions() emits a
# can_read list that is a SUPERSET of real access — it stops at "a role grants a read
# rule" and never runs the full has_permission() check (user permissions, permlevel,
# if_owner). Result: doctypes the user genuinely cannot read (e.g. Stock Entry for a
# Merchandiser) still appear in can_read and leak into the UI. We recompute the
# permission lists for exactly these candidates using the authoritative
# frappe.has_permission() so every SPA gate hides what the user truly can't access.
WEB_DOCTYPES = (
	"SD YRP Cutting Plan",
	"SD YRP Sewing Plan",
	"SD YRP Sewing Plan Entry Detail",
	"SD YRP Finishing Plan",
	"SD YRP Finishing Plan Dispatch",
	"SD YRP Lot",
	"YRP Work Order",
	"YRP Work Order Correction",
	"YRP Debit",
	"YRP Delivery Challan",
	"YRP Goods Received Note",
	"YRP Process Cost",
	"SD YRP Lot Transfer",
	"YRP Stock Entry",
	"Item",
	"YRP Item Price",
	"YRP Item Production Detail",
	"YRP Production Order",
	"YRP Terms and Condition",
	"SD YRP Product",
	"SD YRP Product Release",
	"SD YRP Lotwise Item Profit",
	"YRP Purchase Invoice",
	"YRP Bill Tracking",
	"Purchase Order",
	"SD YRP Cut Panel Movement",
	"SD YRP Cut Bundle Edit",
	"SD YRP Box Sticker Print",
	"YRP Excel Sticker Print",
	"SD YRP Cutting Order",
	"SD YRP Cutting Bulk Lay Sheets",
	"SD YRP Cutting Laysheet Planner",
	"SD YRP Essdee Quality Inspection",
)

# boot.user key -> has_permission ptype used by the SPA's usePermissions composable.
_PTYPE_KEYS = {
	"can_read": "read",
	"can_create": "create",
	"can_write": "write",
	"can_submit": "submit",
	"can_cancel": "cancel",
	"can_delete": "delete",
}


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/web"
		raise frappe.Redirect

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()

	context.csrf_token = csrf_token
	context.boot = get_boot()
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
	assets_dir = os.path.join(os.path.dirname(__file__), "..", "public", "frontend", "assets")
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


def _apply_accurate_web_perms(user):
	"""Overwrite the SPA's candidate DocTypes in each boot permission list with the
	authoritative has_permission() verdict for the current session user, so the UI
	never shows a DocType the user cannot actually access. Administrator/System
	Manager naturally pass has_permission for all, so they keep full visibility."""
	for key, ptype in _PTYPE_KEYS.items():
		allowed = set(user.get(key) or [])
		for dt in WEB_DOCTYPES:
			if frappe.has_permission(dt, ptype):
				allowed.add(dt)
			else:
				allowed.discard(dt)
		user[key] = sorted(allowed)
	return user


def get_boot():
	user = json.loads(frappe.as_json(frappe.get_user().load_user()))
	_apply_accurate_web_perms(user)
	user["full_name"], user["user_image"] = frappe.db.get_value("User", user["name"], ["full_name", "user_image"])
	return {
		"site_name": frappe.local.site,
		# The SPA uses the separate socket port only under the development server.
		"socketio_port": frappe.conf.socketio_port or 9000,
		"dev_server": bool(frappe._dev_server),
		# Desk's logo: Website Settings / Navbar Settings app_logo, else the app_logo_url hook.
		"app_logo": get_app_logo(),
		"user": user,
		# Per-user UI config is resolved by Essdee and injected synchronously.
		# On failure, the SPA uses its compiled-in workspace defaults.
		"ui_config": _safe_ui_config(),
	}


def _safe_ui_config():
	"""Boot must survive ui_config raising ANYTHING (spec §8.1, §14 row 16).

	``get_config_for_boot`` already catches its own exceptions and returns
	``{"config": ..., "meta": ...}`` or ``None`` — this wrapper additionally
	survives the import itself failing (e.g. a base-yrp deploy mid-flight), so
	the /web page can never 500 because of UI config."""
	try:
		from essdee_yrp.ui_config import get_config_for_boot

		return get_config_for_boot()
	except Exception:
		# The log write itself must also be guarded — if Error Log insertion
		# raises (DB trouble, log table locked), boot still must not 500.
		try:
			frappe.log_error(title="/web: ui_config boot failure")
		except Exception:
			pass
		return None
