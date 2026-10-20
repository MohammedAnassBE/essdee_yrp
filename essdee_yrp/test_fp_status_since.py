"""Status timestamps stay stable on saves and change with every transition."""

import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.finishing import status


class TestFPStatusSince(TestCase):
	@patch.object(status, "now", return_value="2026-05-15 12:30:00")
	def test_auto_status_updates_timestamp_only_when_status_changes(self, _now):
		plan = SimpleNamespace(fp_status="Partially Dispatched", fp_status_since="2026-04-01 10:00:00")
		with patch.object(status, "compute_received_status", return_value="Dispatched"):
			status.apply_auto_fp_status(plan)
		self.assertEqual(plan.fp_status, "Dispatched")
		self.assertNotEqual(plan.fp_status_since, "2026-04-01 10:00:00")
		since = plan.fp_status_since
		with patch.object(status, "compute_received_status", return_value="Dispatched"):
			status.apply_auto_fp_status(plan)
		self.assertEqual(plan.fp_status_since, since)

	@patch.object(status, "now", return_value="2026-05-15 12:30:00")
	def test_save_catches_direct_changes_but_preserves_unrelated_save(self, _now):
		previous = SimpleNamespace(fp_status="Dispatched")
		plan = SimpleNamespace(
			fp_status="Fully Dispatched",
			fp_status_since="2026-04-01 10:00:00",
			get_doc_before_save=lambda: previous,
		)
		status.track_fp_status_since(plan)
		self.assertNotEqual(plan.fp_status_since, "2026-04-01 10:00:00")
		since = plan.fp_status_since
		previous.fp_status = plan.fp_status
		status.track_fp_status_since(plan)
		self.assertEqual(plan.fp_status_since, since)


class TestStatusSinceBackfill(TestCase):
	def test_backfill_updates_only_missing_dates_with_current_source_status_history(self):
		script = Path(__file__).resolve().parents[1] / "scripts" / "backfill_finishing_plan_status_since.py"
		plan_backfill = runpy.run_path(str(script))["plan_backfill"]
		history = [
			{
				"name": "FP-1",
				"fp_status": "Dispatched",
				"versions": [
					{
						"docname": "FP-1",
						"creation": "2026-05-15 12:30:00",
						"data": {"changed": [["fp_status", "Planned", "Dispatched"]]},
					}
				],
			}
		]
		targets = [{"name": "FP-1", "fp_status": "Dispatched", "fp_status_since": None}]
		updates, counts = plan_backfill(targets, history)
		self.assertEqual(
			updates, [{"name": "FP-1", "fp_status": "Dispatched", "fp_status_since": "2026-05-15 12:30:00"}]
		)
		self.assertEqual(counts["to_update"], 1)
		updates, counts = plan_backfill([{**targets[0], "fp_status_since": "2026-05-15 12:30:00"}], history)
		self.assertEqual(updates, [])
		self.assertEqual(counts["unchanged"], 1)
		updates, counts = plan_backfill([{**targets[0], "fp_status": "Fully Dispatched"}], history)
		self.assertEqual(updates, [])
		self.assertEqual(counts["status_mismatch"], 1)
		updates, counts = plan_backfill([{**targets[0], "fp_status_since": "2026-10-19 12:00:00"}], history)
		self.assertEqual(updates, [])
		self.assertEqual(counts["existing_preserved"], 1)
