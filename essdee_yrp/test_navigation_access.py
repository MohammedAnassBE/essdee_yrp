import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import navigation_access
from essdee_yrp.navigation_access import (
	NOT_PERMITTED,
	get_place_for_path,
	get_redirect_path,
	has_web_access,
	is_allowed,
)
from essdee_yrp.test_cls_grammage_approval import make_user

DESK_ROLE = "Accounts User"
WEB_ROLE = "Stock User"
DESK_USER = "nav.desk@test.local"
WEB_USER = "nav.web@test.local"
BOTH_USER = "nav.both@test.local"
NEITHER_USER = "nav.neither@test.local"
MANAGER = "nav.manager@test.local"


def set_access_roles(desk_roles, web_roles):
	settings = frappe.get_single(navigation_access.SETTINGS)
	settings.set("desk_access_roles", [{"role": role} for role in desk_roles])
	settings.set("web_access_roles", [{"role": role} for role in web_roles])
	settings.save(ignore_permissions=True)


class TestNavigationAccess(IntegrationTestCase):
	def setUp(self):
		make_user(DESK_USER, [DESK_ROLE])
		make_user(WEB_USER, [WEB_ROLE])
		make_user(BOTH_USER, [DESK_ROLE, WEB_ROLE])
		make_user(NEITHER_USER, ["Purchase User"])
		make_user(MANAGER, ["System Manager"])

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_empty_lists_keep_everyone_allowed(self):
		set_access_roles([], [])
		for user in (DESK_USER, WEB_USER, NEITHER_USER):
			self.assertIsNone(get_redirect_path("desk", user))
			self.assertIsNone(get_redirect_path("web", user))

	def test_both_lists_send_each_user_to_their_place(self):
		set_access_roles([DESK_ROLE], [WEB_ROLE])
		self.assertIsNone(get_redirect_path("desk", DESK_USER))
		self.assertEqual(get_redirect_path("web", DESK_USER), "/desk")
		self.assertIsNone(get_redirect_path("web", WEB_USER))
		self.assertEqual(get_redirect_path("desk", WEB_USER), "/web")
		self.assertIsNone(get_redirect_path("desk", BOTH_USER))
		self.assertIsNone(get_redirect_path("web", BOTH_USER))

	def test_user_allowed_nowhere_gets_not_permitted_not_a_loop(self):
		set_access_roles([DESK_ROLE], [WEB_ROLE])
		self.assertEqual(get_redirect_path("desk", NEITHER_USER), NOT_PERMITTED)
		self.assertEqual(get_redirect_path("web", NEITHER_USER), NOT_PERMITTED)

	def test_one_list_set_leaves_other_place_open(self):
		set_access_roles([DESK_ROLE], [])
		self.assertEqual(get_redirect_path("desk", WEB_USER), "/web")
		self.assertIsNone(get_redirect_path("web", DESK_USER))

	def test_administrator_and_system_manager_always_allowed(self):
		set_access_roles([DESK_ROLE], [WEB_ROLE])
		for user in ("Administrator", MANAGER):
			self.assertTrue(is_allowed("desk", user))
			self.assertTrue(is_allowed("web", user))

	def test_apps_screen_entry_follows_web_roles(self):
		set_access_roles([], [WEB_ROLE])
		frappe.set_user(WEB_USER)
		self.assertTrue(has_web_access())
		frappe.set_user(DESK_USER)
		self.assertFalse(has_web_access())

	def test_place_for_path(self):
		for path in ("/app", "/app/item", "/apps", "/desk", "/desk/item/x"):
			self.assertEqual(get_place_for_path(path, "System User"), "desk")
		self.assertEqual(get_place_for_path("/", "System User"), "desk")
		self.assertIsNone(get_place_for_path("/", "Website User"))
		self.assertEqual(get_place_for_path("/web", "System User"), "web")
		self.assertEqual(get_place_for_path("/web/cutting", "System User"), "web")
		for path in ("/api/method/ping", "/assets/x.js", "/login", "/logout", "/webform", "/message"):
			self.assertIsNone(get_place_for_path(path, "System User"))
