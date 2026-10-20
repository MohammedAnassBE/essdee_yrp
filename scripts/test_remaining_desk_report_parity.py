"""Check worker 5 parity normalisation, comparison and exit status."""

import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
	"remaining_desk_report_parity", Path(__file__).with_name("remaining_desk_report_parity.py")
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)

SOURCE_PAGE = {
	"status": 200,
	"show_stock": True,
	"data": [
		{
			"item_name": "Tee",
			"attribute_values": {"Colour": "Red"},
			"qty": {"default": 0, "S": 2, "M": 0, "stock": {"default": 0, "S": {"val": 4}, "M": {"val": 0}}},
		},
		{
			"item_name": "Plain",
			"attribute_values": {},
			"qty": {"default": 7, "stock": {"default": {"val": 1}}},
		},
	],
}
TARGET_COLUMNS = [
	{"fieldname": "serial_no", "label": "S.No"},
	{"fieldname": "item", "label": "Item Name"},
	{"fieldname": "secondary_0", "label": "Colour"},
	{"fieldname": "type", "label": "Type"},
	{"fieldname": "size_0", "label": "M"},
	{"fieldname": "size_1", "label": "S"},
	{"fieldname": "quantity", "label": "Quantity"},
	{"fieldname": "total_boxes", "label": "Total Boxes"},
]


def target_row(serial, item, colour, kind, m, s, quantity):
	return dict(
		serial_no=serial,
		item=item,
		secondary_0=colour,
		type=kind,
		size_0=m,
		size_1=s,
		quantity=quantity,
		total_boxes=m + s + quantity,
	)


TARGET_ROWS = [
	target_row(1, "Tee", "Red", "Order", 0, 2, 0),
	target_row(1, "Tee", "Red", "Stock", 0, 4, 0),
	target_row(2, "Plain", None, "Order", 0, 0, 7),
	target_row(2, "Plain", None, "Stock", 0, 0, 1),
]


class TestRemainingDeskReportParity(unittest.TestCase):
	def test_source_page_and_target_matrix_normalise_to_the_same_rows(self):
		source = runner.page_rows(SOURCE_PAGE, "C1-1")
		target = runner.matrix_rows(TARGET_COLUMNS, TARGET_ROWS)
		self.assertEqual(runner.sort_rows(source), runner.sort_rows(target))

	def test_successful_sales_cases_are_compared(self):
		source = {"status": "executed", "page": SOURCE_PAGE}
		target = {"status": "executed", "columns": TARGET_COLUMNS, "rows": TARGET_ROWS}
		self.assertTrue(runner.compare("C1-1", source, target)["rows_equal"])
		target["rows"] = TARGET_ROWS[:1]
		self.assertFalse(runner.compare("C1-1", source, target)["rows_equal"])

	def test_failed_execution_is_not_equal(self):
		entry = runner.compare("C2-1", {"status": "error", "error": "missing"}, {"status": "executed"})
		self.assertIsNone(entry["rows_equal"])
		self.assertEqual(entry["status"], "execution error")

	def test_exit_status_is_nonzero_unless_every_case_is_equal(self):
		self.assertEqual(runner.exit_status([{"rows_equal": True}]), 0)
		self.assertEqual(runner.exit_status([{"rows_equal": True}, {"rows_equal": False}]), 1)
		self.assertEqual(runner.exit_status([{"rows_equal": None}]), 1)

	def test_packed_target_receives_posting_dates(self):
		filters = {"start_date": "2026-09-01 00:00:00", "end_date": "2026-09-30 23:59:59"}
		self.assertEqual(
			runner.target_filters("C2-1", filters), {"start_date": "2026-09-01", "end_date": "2026-09-30"}
		)
		self.assertEqual(runner.target_filters("C1-2", {"warehouse": ["S-0056"]}), {"warehouse": ["S-0056"]})


if __name__ == "__main__":
	unittest.main()
