"""Restored ERP Users retain aliases even when source Users swap them."""

import unittest
from copy import deepcopy
from unittest.mock import patch

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.live import _reconcile_approved_user_unique_values


class UserAliasReassignmentTest(unittest.TestCase):
	def test_existing_users_keep_swapped_target_aliases(self):
		for fieldname in ("username", "mobile_no", "api_key"):
			for dry_run in (True, False):
				with self.subTest(fieldname=fieldname, dry_run=dry_run):
					docs = [
						{"doctype": "User", "name": "a@example.com", fieldname: "old-b"},
						{"doctype": "User", "name": "b@example.com", fieldname: "old-a"},
					]
					expected = deepcopy(docs)
					with (
						patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True),
						patch("essdee_yrp.migration.live.frappe.get_all") as read_aliases,
						patch("essdee_yrp.migration.live.frappe.db.set_value") as write,
					):
						result = _reconcile_approved_user_unique_values(docs, dry_run=dry_run)
					read_aliases.assert_not_called()
					write.assert_not_called()
					self.assertEqual(docs, expected)
					self.assertEqual(result["planned_alias_reassignments"], 0)
					self.assertEqual(result["released_migrating_aliases"], 0)

	def test_new_user_cannot_take_alias_from_existing_source_user(self):
		docs = [
			{"doctype": "User", "name": "a", "username": "kept"},
			{"doctype": "User", "name": "b", "username": "source-change"},
		]
		with (
			patch("essdee_yrp.migration.live.frappe.db.exists", side_effect=lambda _dt, name: name == "b"),
			patch("essdee_yrp.migration.live.frappe.get_all", return_value=["b"]),
			patch("essdee_yrp.migration.live.frappe.db.set_value") as write,
		):
			result = _reconcile_approved_user_unique_values(docs, dry_run=False)
		write.assert_not_called()
		self.assertIsNone(docs[0]["username"])
		self.assertEqual(result["preserved_target_users"], 1)

	def test_duplicate_new_source_alias_is_rejected_before_writes(self):
		docs = [{"doctype": "User", "name": name, "username": "same"} for name in ("a", "b")]
		with (
			patch("essdee_yrp.migration.live.frappe.db.exists", return_value=False),
			patch("essdee_yrp.migration.live.frappe.get_all", return_value=[]),
			patch("essdee_yrp.migration.live.frappe.db.set_value") as write,
		):
			with self.assertRaisesRegex(MigrationError, "share unique field"):
				_reconcile_approved_user_unique_values(docs, dry_run=False)
		write.assert_not_called()
