"""Runtime acceptance gates for the migrated Production API Desk surface."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import frappe
from frappe.desk.form.load import getdoc
from frappe.tests import IntegrationTestCase

from essdee_yrp import hooks as app_hooks
from essdee_yrp.cutting.reports import (
	get_daily_production_summary_report,
	get_multiccr,
)

# Parent DocTypes that had a Python controller in the frozen F15 Production API
# source. Renamed concepts point at their reviewed F16 replacement.
PARENT_DOCTYPE_OUTCOMES = {
	"Additional Parameter Key": "Additional Parameter Key",
	"Additional Parameter Value": "Additional Parameter Value",
	"AQL Level": "AQL Level",
	"Brand": "Brand",
	"Company Settings": "Company Settings",
	"Cut Bundle Edit": "Cut Bundle Edit",
	"Cut Bundle Movement Ledger": "Cut Bundle Movement Ledger",
	"Cut Panel Movement": "Cut Panel Movement",
	"Cutter": "Cutter",
	"Cutting LaySheet": "Cutting LaySheet",
	"Cutting Laysheet Planner": "Cutting Laysheet Planner",
	"Cutting Marker": "Cutting Marker",
	"Cutting Order": "Cutting Order",
	"Cutting Order Detail": "Cutting Order Detail",
	"Cutting Plan": "Cutting Plan",
	"Cutting Spreader": "Cutting Spreader",
	"Delivery Challan": "Delivery Challan",
	"Department": "Department",
	"Essdee Debit": "Debit",
	"Essdee Quality Inspection": "Essdee Quality Inspection",
	"Excel Sticker Print": "Excel Sticker Print",
	"FG Item Size Type": "FG Item Size Type",
	"Finishing Plan": "Finishing Plan",
	"Finishing Plan Dispatch": "Finishing Plan Dispatch",
	"Goods Received Note": "Goods Received Note",
	"GRN Item Type": "Received Type",
	"GRN Rework Item": "GRN Rework Item",
	"Item": "Item",
	"Item Alternative": "Item Alternative",
	"Item Attribute": "Item Attribute",
	"Item Attribute Value": "Item Attribute Value",
	"Item BOM Attribute Mapping": "Item BOM Attribute Mapping",
	"Item Category": "Item Category",
	"Item Dependent Attribute Mapping": "Item Dependent Attribute Mapping",
	"Item Group": "Item Group",
	"Item Item Attribute Mapping": "Item Item Attribute Mapping",
	"Item Lead Time": "Item Lead Time",
	"Item Price": "Item Price",
	"Item Variant": "Item Variant",
	"Location": "Location",
	"Lot Template": "Lot Template",
	"MRP Settings": "MRP Settings",
	"Notification Template": "Notification Template",
	"P and L Document": "P and L Document",
	"PPO Price Request": "PPO Price Request",
	"Process": "Process",
	"Process Cost": "Process Cost",
	"Product Category": "Product Category",
	"Production Order": "Production Order",
	"Production Term": "Production Term",
	"Purchase Invoice": "Purchase Invoice",
	"Purchase Order": "Purchase Order",
	"Purchase Order Log": "Purchase Order Log",
	"Recut and Print Panel": "Recut and Print Panel",
	"Sales Item Price": "Sales Item Price",
	"Sales Piece Sticker Print": "Sales Piece Sticker Print",
	"Sewing Plan": "Sewing Plan",
	"Sewing Plan Entry Detail": "Sewing Plan Entry Detail",
	"Sewing Plan Input Type": "Sewing Plan Input Type",
	"Shortened Link": "Shortened Link",
	"Signature": "Signature",
	"Supplier": "Supplier",
	"Tax Slab": "Tax Slab",
	"Telegram Approval Request": "Telegram Approval Request",
	"Telegram Approval Settings": "Telegram Approval Settings",
	"Terms and Condition": "Terms and Condition",
	"UOM": "UOM",
	"Vendor Bill Delivery Person": "Vendor Bill Delivery Person",
	"Vendor Bill Tracking": "Bill Tracking",
	"WO Recut": "WO Recut",
	"Work Order": "Work Order",
}

EXPECTED_EMPTY_DOCTYPES = {
	"Item Lead Time",
	"P and L Document",
	"Purchase Order Log",
	"WO Recut",
}

SAFE_ZERO_ARGUMENT_READ_METHODS = (
	"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.can_approve_grammage",
	"essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan.can_change_approval_grammage",
	"essdee_yrp.essdee_yrp.doctype.lot.lot.check_enabled_po",
	"essdee_yrp.essdee_yrp.doctype.product_image.product_image.get_image_list",
	"essdee_yrp.essdee_yrp.doctype.sales_piece_sticker_print.sales_piece_sticker_print.get_print_format",
	"essdee_yrp.ipd_ui.get_approval_roles",
	"essdee_yrp.ipd_ui.get_ipd_item_group",
	"essdee_yrp.time_and_action.tracking.get_t_and_a_report_data",
	"essdee_yrp.time_and_action.tracking.get_t_and_a_review_report_data",
	"yrp.stock.api.get_stock_dimensions_for_ui",
	"yrp.whatsapp_notification.get_enabled_whatsapp_doctypes",
	"yrp.yrp.api.ui_config.get_my_ui_config",
	"yrp.yrp.api.ui_config.get_my_ui_overrides",
	"yrp.yrp.doctype.goods_received_note.goods_received_note.get_rework_output_received_types",
	"yrp.yrp.doctype.work_order.work_order.get_close_permission",
)

EXPECTED_NON_METHOD_REFERENCES = {
	"essdee_yrp.essdee_yrp.doctype.box_sticker_print.box_sticker_print",
	"essdee_yrp.essdee_yrp.doctype.cutting_bulk_lay_sheets.cutting_bulk_lay_sheets",
	"essdee_yrp.essdee_yrp.doctype.cut_panel_movement.cut_panel_movement",
	"essdee_yrp.essdee_yrp.doctype.essdee_quality_inspection.essdee_quality_inspection",
	"essdee_yrp.essdee_yrp.doctype.finishing_plan_dispatch.finishing_plan_dispatch",
	"essdee_yrp.essdee_yrp.doctype.grn_rework_item.grn_rework_item",
	"essdee_yrp.essdee_yrp.doctype.item_conversion.item_conversion.",
	"essdee_yrp.essdee_yrp.doctype.stock_summary.stock_summary.",
	"essdee_yrp.mrp_stock",
	"yrp.yrp.doctype.item.item.",
}

SUBMITTED_DOC_EVENTS = {
	"before_update_after_submit",
	"on_update_after_submit",
	"on_submit",
	"before_cancel",
	"on_cancel",
}

DRAFT_VALIDATION_EVENTS = {"before_validate", "validate", "before_submit"}

DOC_EVENT_SPECIAL_SAMPLES = {
	("Production Order", "before_cancel"): "PPO-00194-2",
	# The latest packing WO has a submitted dispatch and is intentionally not
	# cancellable. Exercise the on-cancel handlers with a migrated packing WO
	# whose generated Finishing Plan has no downstream dispatch instead.
	("Work Order", "on_cancel"): "WO-2627-00478",
	("Work Order Correction", "before_submit"): "WOC-2026-00001",
}

DOC_EVENT_FILTERS = {
	# Approved IPDs intentionally reject before_validate/validate mutations.
	# Use a real draft migration sample when exercising the handler inventory.
	"Item Production Detail": {"approval_status": ["!=", "Approved"]},
	# Stale draft Stock Entries can legitimately retain a CPM that was later
	# linked elsewhere. The handler inventory uses an unrelated entry; the CPM
	# rejection and lifecycle are covered by the cutting integration matrix.
	"Stock Entry": {"cut_panel_movement": ["is", "not set"]},
}


class TestRuntimeAcceptance(IntegrationTestCase):
	def test_all_essdee_doc_event_handlers_execute(self):
		handled = 0
		for doctype, events in app_hooks.doc_events.items():
			for event, handlers in events.items():
				if not isinstance(handlers, (list, tuple)):
					handlers = [handlers]
				for handler in handlers:
					with self.subTest(doctype=doctype, event=event, handler=handler):
						savepoint = f"runtime_hook_{handled}"
						frappe.db.savepoint(savepoint)
						try:
							name = DOC_EVENT_SPECIAL_SAMPLES.get((doctype, event))
							if not name:
								filters = dict(DOC_EVENT_FILTERS.get(doctype, {}))
								if event in SUBMITTED_DOC_EVENTS:
									filters["docstatus"] = 1
								elif event in DRAFT_VALIDATION_EVENTS:
									filters["docstatus"] = 0
								names = frappe.get_all(
									doctype,
									filters=filters,
									order_by="modified desc",
									pluck="name",
									limit=1,
								)
								self.assertTrue(names, f"No runtime sample for {doctype} / {event}")
								name = names[0]

							doc = frappe.get_doc(doctype, name)
							if doctype == "Production Order" and event == "before_submit":
								frappe.set_user("emp+ansil@essdee.fit")
							frappe.get_attr(handler)(doc, event)
							handled += 1
						finally:
							frappe.set_user("Administrator")
							frappe.db.rollback(save_point=savepoint)

		expected = sum(
			len(handlers) if isinstance(handlers, (list, tuple)) else 1
			for events in app_hooks.doc_events.values()
			for handlers in events.values()
		)
		self.assertEqual(handled, expected)

	def test_all_71_parent_doctype_outcomes_load_or_have_sample_coverage(self):
		self.assertEqual(len(PARENT_DOCTYPE_OUTCOMES), 71)
		for source_doctype, target_doctype in PARENT_DOCTYPE_OUTCOMES.items():
			with self.subTest(source=source_doctype, target=target_doctype):
				meta = frappe.get_meta(target_doctype)
				self.assertFalse(meta.istable)
				if meta.issingle:
					name = target_doctype
				else:
					name = frappe.get_all(
						target_doctype,
						order_by="modified desc",
						pluck="name",
						limit=1,
					)
					if not name:
						self.assertIn(target_doctype, EXPECTED_EMPTY_DOCTYPES)
						continue
					name = name[0]

				frappe.local.response = frappe._dict({"docs": []})
				getdoc(target_doctype, name)
				loaded = next(
					row
					for row in frappe.response.docs
					if row.doctype == target_doctype and row.name == name
				)
				self.assertEqual(json.loads(loaded.as_json())["name"], name)

	def test_four_empty_parent_doctypes_accept_rollback_safe_samples(self):
		item = frappe.get_all("Item", pluck="name", limit=1)[0]
		work_order = frappe.db.sql(
			"""
			SELECT wo.name
			FROM `tabWork Order` wo
			INNER JOIN `tabWork Order Calculated Item` item ON item.parent = wo.name
			WHERE wo.docstatus = 1
			  AND wo.open_status = 'Open'
			  AND COALESCE(wo.is_rework, 0) = 0
			  AND item.quantity > 0
			ORDER BY wo.modified DESC
			LIMIT 1
			""",
		)[0][0]
		work_order_doc = frappe.get_doc("Work Order", work_order)
		calculated_item = next(
			row for row in work_order_doc.work_order_calculated_items if row.quantity > 0
		)

		samples = (
			frappe.get_doc(
				{
					"doctype": "Item Lead Time",
					"item_name": item,
					"lead_time": 1,
				}
			),
			frappe.get_doc(
				{
					"doctype": "P and L Document",
					"against": "Item",
					"against_id": item,
					"comments": "Runtime acceptance sample",
				}
			),
			frappe.get_doc(
				{
					"doctype": "Purchase Order Log",
					"type": "Runtime Acceptance",
					"reason": "Rollback-safe lifecycle sample",
				}
			),
			frappe.get_doc(
				{
					"doctype": "WO Recut",
					"work_order": work_order,
					"wo_recut_details": [
						{
							"item_variant": calculated_item.item_variant,
							"quantity": 1,
							"table_index": calculated_item.table_index,
							"row_index": calculated_item.row_index,
						}
					],
				}
			),
		)

		for sample in samples:
			with self.subTest(doctype=sample.doctype):
				sample.insert(ignore_permissions=True)
				self.assertFalse(sample.is_new())
				sample.run_method("onload")

		wo_recut = samples[-1]
		wo_recut.submit()
		self.assertEqual(wo_recut.docstatus, 1)
		wo_recut.cancel()
		self.assertEqual(wo_recut.docstatus, 2)

		with self.assertRaises(frappe.ValidationError):
			samples[2].run_method("on_cancel")

	def test_all_static_ui_server_references_resolve_and_are_whitelisted(self):
		root = Path(frappe.get_app_path("essdee_yrp"))
		pattern = re.compile(r'''["']((?:essdee_yrp|yrp)\.[A-Za-z0-9_.$]+)["']''')
		references = set()
		for path in (*root.rglob("*.js"), *root.rglob("*.vue")):
			if {"node_modules", "dist"}.intersection(path.parts):
				continue
			references.update(pattern.findall(path.read_text(errors="ignore")))
		references = {reference for reference in references if "${" not in reference}
		references.difference_update(EXPECTED_NON_METHOD_REFERENCES)

		unresolved = set()
		resolved = []
		for reference in references:
			try:
				resolved.append((reference, frappe.get_attr(reference)))
			except (AttributeError, ImportError, ModuleNotFoundError):
				unresolved.add(reference)

		self.assertFalse(unresolved)
		for reference, function in resolved:
			with self.subTest(method=reference):
				self.assertIn(function, frappe.whitelisted)

	def test_zero_argument_read_endpoints_execute(self):
		for method in SAFE_ZERO_ARGUMENT_READ_METHODS:
			with self.subTest(method=method):
				function = frappe.get_attr(method)
				self.assertFalse(
					[
						parameter
						for parameter in inspect.signature(function).parameters.values()
						if parameter.default is inspect.Parameter.empty
						and parameter.kind
						not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
					]
				)
				function()

	def test_contextual_read_endpoints_execute_on_migrated_records(self):
		cutting_plan = frappe.get_doc("Cutting Plan", "CP-2608-00006")
		lot = cutting_plan.lot

		get_daily_production_summary_report(
			from_date="2099-01-01",
			to_date="2099-01-02",
		)
		multiccr = get_multiccr(lot_list=json.dumps(["F1024-54"]))
		self.assertIn("data", multiccr)

		calls = (
			(
				"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_cloth_accessories",
				{"cutting_plan": cutting_plan.name},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.cutting_laysheet.cutting_laysheet.get_select_attributes",
				{"cutting_plan": cutting_plan.name},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.cutting_marker.cutting_marker.calculate_parts",
				{"cutting_plan": cutting_plan.name},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.cutting_marker.cutting_marker.get_primary_and_bundle_detail",
				{
					"lot": lot,
					"selected_value": "Machine",
					"panels": [],
					"grp_panels": [],
				},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.finishing_plan.finishing_plan.get_primary_values",
				{"lot": lot},
			),
		)
		for method, kwargs in calls:
			with self.subTest(method=method):
				frappe.get_attr(method)(**kwargs)
