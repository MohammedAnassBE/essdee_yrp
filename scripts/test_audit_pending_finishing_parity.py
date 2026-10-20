"""The parity checker must fail on changed dates, cells, and missing plans."""
import copy
import unittest

from audit_pending_finishing_parity import compare_payloads


def fixture():
	return {
		"queues": {"default": {"summary": {"overdue": 1}, "plans": [
			{"name": "FP-1", "status_since": "2026-05-15", "age_days": 158,
			 "fp_status": "Dispatched", "total_cut": 10, "sewing_received": 9,
			 "packed": 8, "dispatched": 7, "dispatch_history": []},
		]}},
		"status_dates": {"FP-1": {"fp_status": "Dispatched", "status_since": "2026-05-15 12:00:00"}},
		"pending": {"FP-1": {"parts": [{"name": "Top", "sizes": ["S"], "categories": [
			{"key": "rejected", "total": 6, "size_totals": [6], "rows": [{"colour": "Blue", "values": [6], "total": 6}]},
		]}]}},
	}


class TestAuditPendingParity(unittest.TestCase):
	def test_equal_payloads_are_successful(self):
		self.assertTrue(compare_payloads(fixture(), fixture())["equal"])

	def test_quantity_float_noise_is_tolerated_but_real_quantity_changes_fail(self):
		source, target = fixture(), fixture()
		source["queues"]["default"]["plans"][0]["packed"] = 934.9999999999998
		target["queues"]["default"]["plans"][0]["packed"] = 935.0
		self.assertTrue(compare_payloads(source, target)["equal"])
		target["queues"]["default"]["plans"][0]["packed"] = 935.01
		self.assertFalse(compare_payloads(source, target)["equal"])

	def test_changed_date_age_cell_and_missing_plan_are_reported(self):
		for mutation in ("date", "age", "cell", "missing"):
			with self.subTest(mutation=mutation):
				source, target = fixture(), copy.deepcopy(fixture())
				if mutation == "date":
					target["status_dates"]["FP-1"]["status_since"] = "2026-05-16 12:00:00"
				elif mutation == "age":
					target["queues"]["default"]["plans"][0]["age_days"] = 157
				elif mutation == "cell":
					target["pending"]["FP-1"]["parts"][0]["categories"][0]["rows"][0]["values"] = [5]
				else:
					target["queues"]["default"]["plans"] = []
				result = compare_payloads(source, target)
				self.assertFalse(result["equal"])
				self.assertTrue(result["differences"])


if __name__ == "__main__":
	unittest.main()
