"""Role-gated navigation between Desk and /web.

`SD YRP MRP Settings` holds two role lists. An empty list leaves that place open
to everyone; Administrator and System Manager are always allowed. This gates page
navigation only: /api and DocType permissions are untouched.
"""

import frappe
from frappe import _
from frappe.website.page_renderers.template_page import TemplatePage
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect

SETTINGS = "SD YRP MRP Settings"
ROLE_FIELDS = {"desk": "desk_access_roles", "web": "web_access_roles"}
PLACE_PATHS = {"desk": "/desk", "web": "/web"}
DESK_ROOTS = {"app", "apps", "desk"}
NOT_PERMITTED = "not-permitted"


def get_access_roles(place):
	rows = frappe.get_cached_doc(SETTINGS).get(ROLE_FIELDS[place]) or []
	return {row.role for row in rows}


def is_allowed(place, user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	allowed_roles = get_access_roles(place)
	return "System Manager" in roles or not allowed_roles or bool(roles & allowed_roles)


def has_web_access():
	"""`add_to_apps_screen` permission check for the /web entry in Desk."""
	return is_allowed("web")


def get_redirect_path(place, user):
	"""None when `user` may open `place`, else the other place's path or NOT_PERMITTED."""
	if is_allowed(place, user):
		return None
	other = "web" if place == "desk" else "desk"
	return PLACE_PATHS[other] if is_allowed(other, user) else NOT_PERMITTED


def get_place_for_path(path, user_type):
	root = path.strip("/").split("/", 1)[0]
	if root in DESK_ROOTS or (root == "" and user_type == "System User"):
		return "desk"
	return "web" if root == "web" else None


def gate_navigation():
	"""before_request hook: redirect page loads of Desk or /web the user may not open."""
	request = getattr(frappe.local, "request", None)
	user = frappe.session.user
	if request is None or user == "Guest":
		return
	place = get_place_for_path(request.path, frappe.session.data.user_type)
	target = place and get_redirect_path(place, user)
	if not target:
		return
	if target == NOT_PERMITTED:
		raise HTTPException(response=get_not_permitted_response())
	raise HTTPException(response=redirect(target, 302))


def get_not_permitted_response():
	frappe.respond_as_web_page(
		_("Not Permitted"),
		_("Your roles do not allow you to open Desk or /web. Ask your administrator for access."),
		http_status_code=403,
		indicator_color="red",
		primary_action="/logout",
		primary_label=_("Log out"),
		fullpage=True,
	)
	return TemplatePage("message", 403).render()
