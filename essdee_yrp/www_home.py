"""Post-login landing for Essdee YRP.

Wired via `get_website_user_home_page` in hooks.py. Frappe calls this for every
logged-in user (see `frappe/website/utils.py::get_home_page_via_hooks`) to pick
their home page.

Policy (user requirement, 2026-07-03): everyone lands on the custom `/web` work
hub EXCEPT `System Manager` and `Administrator`, who keep the Desk default.
Returning `None` lets Frappe fall through to its normal resolution
(workspace / desk) for those privileged users.
"""

import frappe

# Roles (and the special Administrator user) that keep the Desk default.
DESK_ROLES = {"System Manager"}


def get_website_user_home_page(user=None):
	"""Return "web" for ordinary users, None for Desk admins (fall through)."""
	user = user or frappe.session.user
	if user in ("Guest", "Administrator"):
		# Guest never reaches here for /web; Administrator keeps Desk.
		return None

	roles = set(frappe.get_roles(user))
	if roles & DESK_ROLES:
		return None  # System Manager keeps the Desk default.

	# Everyone else lands on the custom work hub. Frappe strips the leading
	# slash, so "web" resolves to /web.
	return "web"
