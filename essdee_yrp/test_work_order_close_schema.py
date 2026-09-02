import json
import unittest
from pathlib import Path


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "custom_field.json"


class TestWorkOrderCloseSchema(unittest.TestCase):
	def test_essdee_close_fields_do_not_change_base_close_reason(self):
		rows = json.loads(FIXTURE.read_text())
		fields = {
			row["fieldname"]: row
			for row in rows
			if row.get("dt") == 'YRP Work Order'
		}
		reason = fields["sd_close_reason"]
		self.assertEqual(reason["fieldtype"], "Select")
		self.assertEqual(reason["module"], "Essdee YRP")
		self.assertIn("Sewing Shortage", reason["options"].splitlines())
		self.assertEqual(fields["close_other_reason"]["fieldtype"], "Data")
		self.assertNotIn("close_reason", fields)

	def test_closed_work_order_sewing_grn_marker_is_storage_only(self):
		rows = json.loads(FIXTURE.read_text())
		field = next(
			row
			for row in rows
			if row.get("dt") == 'YRP Goods Received Note'
			and row.get("fieldname") == "from_closed_wo_sewing_details"
		)
		self.assertEqual(field["fieldtype"], "Check")
		self.assertEqual(field["default"], "0")
		self.assertEqual(field["module"], "Essdee YRP")
		self.assertTrue(field["hidden"])
		self.assertTrue(field["read_only"])
		self.assertTrue(field["no_copy"])


if __name__ == "__main__":
	unittest.main()
