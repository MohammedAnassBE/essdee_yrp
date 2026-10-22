import frappe
from frappe import _
from frappe.core.doctype.activity_log.activity_log import add_authentication_log
from frappe.core.doctype.user.user import update_password as frappe_update_password
from frappe.sessions import clear_sessions
from frappe.utils.password import check_password


@frappe.whitelist(methods=["POST"])
def update_password(old_password: str, new_password: str):
	"""Frappe's update_password, except a wrong old password does not clear this session's cookies."""
	try:
		check_password(frappe.session.user, old_password)
	except frappe.AuthenticationError:
		add_authentication_log("Incorrect password", frappe.session.user, status="Failed")
		frappe.db.commit()  # keep the failed-attempt log, as LoginManager.fail does
		frappe.throw(_("Your old password is incorrect."))
	return frappe_update_password(new_password=new_password, old_password=old_password, logout_all_sessions=1)


@frappe.whitelist(methods=["POST"])
def logout_other_sessions():
	"""End the current user's other sessions, as Frappe's forced logout does; the caller then logs out."""
	clear_sessions(user=frappe.session.user, keep_current=True, force=True)
