from contextlib import ExitStack
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.patches import add_web_read_indexes as indexes


class TestWebReadIndexes(TestCase):
	def run_patch(self, existing=(), missing_fields=(), missing_tables=()):
		created = []
		current = list(existing)
		def add(doctype, columns, name):
			created.append((doctype, columns, name))
			current.extend(frappe._dict(Key_name=name, Seq_in_index=i + 1, Column_name=col) for i, col in enumerate(columns))
		with (
			patch.object(frappe.db, "table_exists", side_effect=lambda dt: dt not in missing_tables),
			patch.object(frappe.db, "has_column", side_effect=lambda dt, col: (dt, col) not in missing_fields),
			patch.object(frappe.db, "sql", side_effect=lambda *a, **kw: current),
			patch.object(frappe.db, "add_index", side_effect=add),
			patch.object(indexes, "CANDIDATES", (("YRP Stock Entry", ("against_id", "against")),)),
		):
			indexes.execute()
			indexes.execute()
		return created

	def test_idempotent_and_existing_longer_prefix_is_coverage(self):
		self.assertEqual(len(self.run_patch()), 1)
		rows = [frappe._dict(Key_name="other", Seq_in_index=i + 1, Column_name=col)
			for i, col in enumerate(("against_id", "against", "docstatus"))]
		self.assertEqual(self.run_patch(rows), [])

	def test_reverse_index_is_not_coverage_and_conflicting_name_is_preserved(self):
		rows = [frappe._dict(Key_name="web_read_against_id_against", Seq_in_index=i + 1, Column_name=col)
			for i, col in enumerate(("against", "against_id"))]
		created = self.run_patch(rows)
		self.assertEqual(len(created), 1)
		self.assertNotEqual(created[0][2], "web_read_against_id_against")

	def test_missing_optional_schema_is_skipped(self):
		self.assertEqual(self.run_patch(missing_tables=("YRP Stock Entry",)), [])
		self.assertEqual(self.run_patch(missing_fields=(("YRP Stock Entry", "against"),)), [])

	def test_migration_setup_restores_indexes_after_schema_sync(self):
		from essdee_yrp import setup

		rows = []
		created = []
		def add(doctype, columns, name):
			created.append(name)
			rows.extend(frappe._dict(Key_name=name, Seq_in_index=i + 1, Column_name=col) for i, col in enumerate(columns))

		# Setup synchronizes custom fields after post-model patches have run.
		setup_tasks = (
			"ensure_historical_quantity_storage", "validate_purchase_invoice_commercial_fields",
			"ensure_process_billing_items", "ensure_yrp_valuation_contract", "ensure_required_stock_dimensions",
			"ensure_stock_transaction_indexes", "ensure_finishing_plan_dispatch_naming_series",
			"ensure_default_address_template", "ensure_variant_flag_fields", "ensure_mrp_schema_roles",
			"ensure_mrp_cancel_permissions", "ensure_production_planner_read_permissions",
			"ensure_sd_yrp_consumer_config", "ensure_yrp_production_order_settings", "ensure_lot_packing_boundary",
			"build_web_spa",
		)
		with ExitStack() as stack:
			for name in setup_tasks:
				stack.enter_context(patch.object(setup, name))
			for name in (
				"essdee_yrp.patches.setup_process_conversion_attributes.sync_existing_process_configuration",
				"essdee_yrp.purchase_invoice.backfill_legacy_commercial_items",
				"essdee_yrp.purchase_invoice.backfill_unprojected_work_order_drafts",
				"essdee_yrp.purchase_order_approval.ensure_purchase_order_approval_route",
			):
				stack.enter_context(patch(name))
			stack.enter_context(patch.object(setup, "ensure_essdee_stock_dimensions", side_effect=rows.clear))
			stack.enter_context(patch.object(indexes, "CANDIDATES", (("YRP Stock Entry", ("cut_panel_movement",)),)))
			stack.enter_context(patch.object(frappe.db, "table_exists", return_value=True))
			stack.enter_context(patch.object(frappe.db, "has_column", return_value=True))
			stack.enter_context(patch.object(frappe.db, "sql", side_effect=lambda *a, **kw: rows))
			stack.enter_context(patch.object(frappe.db, "add_index", side_effect=add))
			indexes.execute()
			for _ in range(2):
				setup.after_migrate()
				self.assertEqual([row.Column_name for row in rows], ["cut_panel_movement"])
			self.assertEqual(len(created), 3)
			indexes.execute()
			self.assertEqual(len(created), 3)
