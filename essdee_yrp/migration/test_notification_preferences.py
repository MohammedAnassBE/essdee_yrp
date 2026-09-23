"""Newer F15 notification preferences must survive the approved export."""
import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

from essdee_yrp.migration.live import APPROVED_FRAPPE_DATA_ORDER


class NotificationPreferenceMigrationTest(unittest.TestCase):
	def export(self, child_doctype):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts/f15_source_bridge.py"))
		export = bridge["iter_approved_frappe_documents"]
		doc = {"doctype": "Notification Settings", "name": "user@example.test",
			"disabled_notification_types": [{"doctype": child_doctype,
				"name": "pref-1", "notification_type": "Assignment"}]}
		with patch.dict(export.__globals__, {
			"_spine_doctypes": lambda _: set(),
			"_approved_frappe_names": lambda _, dt, __: [doc["name"]] if dt == "Notification Settings" else [],
			"_approved_frappe_document": lambda *args, **kwargs: doc,
		}):
			return list(export(None)), bridge

	def test_preserves_preference_child_and_orders_linked_master_first(self):
		docs, bridge = self.export("Notification Type Preference")
		self.assertEqual(docs[0]["disabled_notification_types"][0]["notification_type"], "Assignment")
		for order in (bridge["APPROVED_FRAPPE_DATA_ORDER"], APPROVED_FRAPPE_DATA_ORDER):
			self.assertLess(order.index("Notification Type"), order.index("Notification Settings"))

	def test_verifier_catalogue_includes_notification_master_and_children(self):
		from essdee_yrp.migration.planner import build_schema_analysis
		plan, _ = build_schema_analysis()
		for doctype in ("Notification Type", "Notification Settings", "Notification Type Preference"):
			self.assertIn(doctype, plan.target_schemas)

	def test_unknown_child_still_rejected(self):
		with self.assertRaisesRegex(RuntimeError, "Unapproved Frappe child"):
			self.export("Unknown Child")
