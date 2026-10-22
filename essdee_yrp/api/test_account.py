from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import update_password as set_password

from essdee_yrp.api.account import logout_other_sessions, update_password

USER = "account-menu-sessions@test.local"
OTHER_USER = "account-menu-other@test.local"


def ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc({"doctype": "User", "email": email, "first_name": "Account Menu", "send_welcome_email": 0}).insert(ignore_permissions=True)


def add_session(user, sid):
	frappe.db.sql(
		"insert into `tabSessions` (user, sid, sessiondata, lastupdate, status) values (%s, %s, '{}', now(), 'Active')",
		(user, sid),
	)


def session_ids(user):
	return set(frappe.db.sql_list("select sid from `tabSessions` where user = %s", user))


class TestLogoutOtherSessions(IntegrationTestCase):
	def setUp(self):
		for email in (USER, OTHER_USER):
			ensure_user(email)
		frappe.set_user(USER)
		self.current_sid = frappe.session.sid
		for sid in ("account-menu-phone", "account-menu-laptop", self.current_sid):
			add_session(USER, sid)
		add_session(OTHER_USER, "account-menu-other")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.sql("delete from `tabSessions` where user in %s", ((USER, OTHER_USER),))
		frappe.db.commit()

	def test_ends_every_other_session_of_the_current_user_only(self):
		logout_other_sessions()
		self.assertEqual(session_ids(USER), {self.current_sid})
		self.assertEqual(session_ids(OTHER_USER), {"account-menu-other"})

	def test_is_a_post_only_method_for_signed_in_users(self):
		self.assertIn(logout_other_sessions, frappe.whitelisted)
		self.assertNotIn(logout_other_sessions, frappe.guest_methods)
		self.assertEqual(frappe.allowed_http_methods_for_whitelisted_func[logout_other_sessions], ["POST"])


class TestUpdatePassword(IntegrationTestCase):
	def setUp(self):
		ensure_user(USER)
		set_password(USER, "Old-Account-Menu-9!")
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_wrong_old_password_is_a_validation_error_so_the_session_survives(self):
		with patch("essdee_yrp.api.account.frappe_update_password") as frappe_update:
			with self.assertRaises(frappe.ValidationError) as raised:
				update_password(old_password="wrong", new_password="New-Account-Menu-7?")
		self.assertNotIsInstance(raised.exception, frappe.AuthenticationError)
		self.assertIn("old password is incorrect", str(raised.exception))
		frappe_update.assert_not_called()

	def test_right_old_password_runs_frappes_update_password(self):
		with patch("essdee_yrp.api.account.frappe_update_password", return_value="/desk") as frappe_update:
			result = update_password(old_password="Old-Account-Menu-9!", new_password="New-Account-Menu-7?")
		self.assertEqual(result, "/desk")
		frappe_update.assert_called_once_with(
			new_password="New-Account-Menu-7?", old_password="Old-Account-Menu-9!", logout_all_sessions=1
		)
