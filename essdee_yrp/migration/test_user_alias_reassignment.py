"""A fresh ERP snapshot must not discard aliases vacated by another source User."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.live import _reconcile_approved_user_unique_values


class UserAliasReassignmentTest(unittest.TestCase):
	def test_swapped_aliases_survive_first_write_and_verification(self):
		for fieldname in ("username", "mobile_no", "api_key"):
			for reverse in (False, True):
				with self.subTest(fieldname=fieldname, reverse=reverse):
					target = {"A@example.com": {fieldname: "old-a"}, "b@example.com": {fieldname: "old-b"}}
					source = [
						{"doctype": "User", "name": "a@example.com", fieldname: "old-b"},
						{"doctype": "User", "name": "b@example.com", fieldname: "old-a"},
					]
					if reverse:
						source.reverse()

					def get_all(_doctype, *, filters, **kwargs):
						return [name for name, row in target.items()
							if name.casefold() != filters["name"][1].casefold()
							and row[fieldname] == filters[fieldname]]

					def set_value(_doctype, filters, field, value, **kwargs):
						self.assertFalse(kwargs["update_modified"])
						row = target[filters["name"]]
						self.assertEqual(row[field], filters[field])
						row[field] = value

					with patch("essdee_yrp.migration.live.frappe.get_all", side_effect=get_all), \
						patch("essdee_yrp.migration.live.frappe.db.set_value", side_effect=set_value) as write:
						expected = deepcopy(source)
						preview = _reconcile_approved_user_unique_values(expected, dry_run=True)
						write.assert_not_called()
						self.assertEqual(preview["planned_alias_reassignments"], 2)
						self.assertEqual(expected, source)
						actual = deepcopy(source)
						result = _reconcile_approved_user_unique_values(actual, dry_run=False)
						self.assertEqual(result["released_migrating_aliases"], 2)
						self.assertEqual(result["cleared_source_aliases"], 0)
						for doc in actual:
							# Model unique-index checks in either insertion order.
							self.assertNotIn(doc[fieldname], [row[fieldname] for row in target.values()])
							name = next(name for name in target if name.casefold() == doc["name"].casefold())
							target[name][fieldname] = doc[fieldname]
						verified = deepcopy(source)
						result = _reconcile_approved_user_unique_values(verified, dry_run=True)
						self.assertEqual(verified, source)
						self.assertEqual(result["planned_alias_reassignments"], 0)

	def test_source_owner_with_unmapped_alias_remains_protected(self):
		docs = [{"doctype": "User", "name": "a", "username": "kept"}, {"doctype": "User", "name": "b"}]
		with patch("essdee_yrp.migration.live.frappe.get_all", return_value=["b"]), \
			patch("essdee_yrp.migration.live.frappe.db.set_value") as write:
			result = _reconcile_approved_user_unique_values(docs, dry_run=False)
		write.assert_not_called()
		self.assertIsNone(docs[0]["username"])
		self.assertEqual(result["preserved_target_users"], 1)

	def test_duplicate_source_alias_is_rejected_before_writes(self):
		docs = [{"doctype": "User", "name": name, "username": "same"} for name in ("a", "b")]
		with patch("essdee_yrp.migration.live.frappe.get_all", return_value=["b"]), \
			patch("essdee_yrp.migration.live.frappe.db.set_value") as write:
			with self.assertRaisesRegex(MigrationError, "share unique field"):
				_reconcile_approved_user_unique_values(docs, dry_run=False)
		write.assert_not_called()
