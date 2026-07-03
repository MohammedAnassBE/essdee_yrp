"""Desk gate for the Essdee /web deployment.

Non-privileged users live in the /web SPA; the Frappe Desk is reserved for
Administrator + System Manager. Wired via `before_request` in hooks.py.

Frappe 16 serves the Desk at /desk; /app, /app/*, and /apps are 301 aliases
(frappe/hooks.py website_redirects), so all four roots are gated. `/` is also
redirected for gated users (the website home resolution would otherwise render
the SPA at URL "/" where the vue-router base /web doesn't match). Guests are
left alone (Frappe's own login redirect handles them). /api, /assets, /files,
/web and websockets are untouched so the SPA keeps working.

A plain `raise frappe.Redirect` does NOT work from before_request (it runs in
init_request, outside the website renderer's exception handler, and would land
on an error page) — raise a werkzeug HTTPException carrying a real 302 instead;
`frappe.app.handle_exception` converts it via `e.get_response()`.

NOTE: this is a NAVIGATIONAL gate, not a security boundary — /api stays open
and role-based DocType permissions remain the real enforcement.
"""

import frappe
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect as _redirect

DESK_ROOTS = {"app", "apps", "desk"}


def block_desk_for_non_managers():
	request = getattr(frappe.local, "request", None)
	if request is None:
		return
	path = (request.path or "").strip("/ ")
	root = path.split("/", 1)[0]
	if root not in DESK_ROOTS and path != "":
		return
	user = getattr(frappe.session, "user", None)
	if not user or user in ("Guest", "Administrator"):
		return
	if "System Manager" in frappe.get_roles(user):
		return
	raise HTTPException(response=_redirect("/web", 302))
