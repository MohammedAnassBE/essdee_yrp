from contextlib import ExitStack
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

import essdee_yrp.setup as setup


class TestEssdeeSetup(FrappeTestCase):
	def test_fresh_install_seeds_dimensions_before_stock_indexes(self):
		calls = []
		steps = (
			"ensure_purchase_invoice_commercial_fields",
			"ensure_process_billing_items",
			"ensure_yrp_valuation_contract",
			"ensure_required_stock_dimensions",
			"ensure_essdee_stock_dimensions",
			"ensure_stock_transaction_indexes",
			"ensure_finishing_plan_dispatch_naming_series",
			"ensure_default_address_template",
			"ensure_mrp_schema_roles",
			"ensure_mrp_cancel_permissions",
			"ensure_sewing_plan_settings",
			"ensure_yrp_production_order_settings",
			"ensure_lot_packing_boundary",
		)
		with ExitStack() as stack:
			for step in steps:
				stack.enter_context(
					patch.object(
						setup,
						step,
						side_effect=lambda step=step: calls.append(step),
					)
				)
			setup.after_install()

		self.assertLess(
			calls.index("ensure_required_stock_dimensions"),
			calls.index("ensure_stock_transaction_indexes"),
		)
		self.assertLess(
			calls.index("ensure_essdee_stock_dimensions"),
			calls.index("ensure_stock_transaction_indexes"),
		)

	def test_required_dimensions_are_seeded_without_replacing_existing_rows(self):
		existing = frappe._dict(
			dimension_doctype="Quality Grade",
			fieldname="quality_grade",
			label="Quality Grade",
		)
		settings = MagicMock()
		settings.stock_dimensions = [existing]

		def append(_fieldname, values):
			row = frappe._dict(values)
			settings.stock_dimensions.append(row)
			return row

		settings.append.side_effect = append
		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_single", return_value=settings),
		):
			setup.ensure_required_stock_dimensions()

		settings.save.assert_called_once_with(ignore_permissions=True)
		rows = {row.fieldname: row for row in settings.stock_dimensions}
		self.assertEqual(set(rows), {"quality_grade", "lot", "received_type"})
		self.assertEqual(rows["lot"].dimension_doctype, "Lot")
		self.assertEqual(rows["lot"].is_production_group, 1)
		self.assertEqual(rows["received_type"].dimension_doctype, "Received Type")
		self.assertEqual(rows["received_type"].in_valuation, 1)

	def test_pymupdf_is_a_runtime_dependency(self):
		pyproject = Path(frappe.get_app_path("essdee_yrp")).parent / "pyproject.toml"
		contents = pyproject.read_text(encoding="utf-8").lower()
		self.assertIn('"pymupdf>=1.26,<2"', contents)
