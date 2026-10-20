import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from essdee_yrp.patches import recalculate_attribute_mapped_finishing_plan_statuses as status_patch


class TestFinishingStatusPatch(unittest.TestCase):
	def test_recalculation_updates_automatic_status_and_preserves_audit_status(self):
		frappe = SimpleNamespace(
			db=SimpleNamespace(set_value=Mock()),
			get_doc=Mock(return_value=SimpleNamespace(name="FP-AUTO")),
		)
		candidates = [
			SimpleNamespace(name="FP-AUTO", fp_status="Partially Dispatched"),
			SimpleNamespace(name="FP-AUDIT", fp_status="Audit Completed"),
		]
		with (
			patch.object(status_patch, "frappe", frappe),
			patch.object(status_patch, "now", return_value="2026-10-20 12:30:00"),
			patch.object(status_patch, "get_candidate_plans", return_value=candidates),
			patch.object(status_patch, "compute_received_status", return_value="Fully Dispatched"),
		):
			result = status_patch.execute()

		frappe.db.set_value.assert_called_once_with(
			"SD YRP Finishing Plan",
			"FP-AUTO",
			{"fp_status": "Fully Dispatched", "fp_status_since": "2026-10-20 12:30:00"},
			update_modified=False,
		)
		self.assertEqual(result, {"total": 2, "updated": 1, "unchanged": 0, "skipped": 1})


if __name__ == "__main__":
	unittest.main()
