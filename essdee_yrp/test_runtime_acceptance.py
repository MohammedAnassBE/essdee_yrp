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
	'YRP Additional Parameter Key': 'YRP Additional Parameter Key',
	'YRP Additional Parameter Value': 'YRP Additional Parameter Value',
	'SD YRP AQL Level': 'SD YRP AQL Level',
	'YRP Brand': 'YRP Brand',
	'SD YRP Company Settings': 'SD YRP Company Settings',
	'SD YRP Cut Bundle Edit': 'SD YRP Cut Bundle Edit',
	'SD YRP Cut Bundle Movement Ledger': 'SD YRP Cut Bundle Movement Ledger',
	'SD YRP Cut Panel Movement': 'SD YRP Cut Panel Movement',
	'SD YRP Cutter': 'SD YRP Cutter',
	'SD YRP Cutting LaySheet': 'SD YRP Cutting LaySheet',
	'SD YRP Cutting Laysheet Planner': 'SD YRP Cutting Laysheet Planner',
	'SD YRP Cutting Marker': 'SD YRP Cutting Marker',
	'SD YRP Cutting Order': 'SD YRP Cutting Order',
	'SD YRP Cutting Order Detail': 'SD YRP Cutting Order Detail',
	'SD YRP Cutting Plan': 'SD YRP Cutting Plan',
	'SD YRP Cutting Spreader': 'SD YRP Cutting Spreader',
	'YRP Delivery Challan': 'YRP Delivery Challan',
	'YRP Department': 'YRP Department',
	"Essdee Debit": 'YRP Debit',
	'SD YRP Essdee Quality Inspection': 'SD YRP Essdee Quality Inspection',
	'YRP Excel Sticker Print': 'YRP Excel Sticker Print',
	'SD YRP FG Item Size Type': 'SD YRP FG Item Size Type',
	'SD YRP Finishing Plan': 'SD YRP Finishing Plan',
	'SD YRP Finishing Plan Dispatch': 'SD YRP Finishing Plan Dispatch',
	'YRP Goods Received Note': 'YRP Goods Received Note',
	"GRN Item Type": 'YRP Received Type',
	'SD YRP GRN Rework Item': 'SD YRP GRN Rework Item',
	'YRP Item': 'YRP Item',
	'SD YRP Item Alternative': 'SD YRP Item Alternative',
	'YRP Item Attribute': 'YRP Item Attribute',
	'YRP Item Attribute Value': 'YRP Item Attribute Value',
	'YRP Item BOM Attribute Mapping': 'YRP Item BOM Attribute Mapping',
	'YRP Item Category': 'YRP Item Category',
	'YRP Item Dependent Attribute Mapping': 'YRP Item Dependent Attribute Mapping',
	'YRP Item Group': 'YRP Item Group',
	'YRP Item Item Attribute Mapping': 'YRP Item Item Attribute Mapping',
	'SD YRP Item Lead Time': 'SD YRP Item Lead Time',
	'YRP Item Price': 'YRP Item Price',
	'YRP Item Variant': 'YRP Item Variant',
	'SD YRP Location': 'SD YRP Location',
	'SD YRP Lot Template': 'SD YRP Lot Template',
	'SD YRP MRP Settings': 'SD YRP MRP Settings',
	'YRP Notification Template': 'YRP Notification Template',
	'SD YRP P and L Document': 'SD YRP P and L Document',
	'SD YRP PPO Price Request': 'SD YRP PPO Price Request',
	'YRP Process': 'YRP Process',
	'YRP Process Cost': 'YRP Process Cost',
	'SD YRP Product Category': 'SD YRP Product Category',
	'YRP Production Order': 'YRP Production Order',
	'YRP Production Term': 'YRP Production Term',
	'YRP Purchase Invoice': 'YRP Purchase Invoice',
	'YRP Purchase Order': 'YRP Purchase Order',
	'SD YRP Purchase Order Log': 'SD YRP Purchase Order Log',
	'SD YRP Recut and Print Panel': 'SD YRP Recut and Print Panel',
	'SD YRP Sales Item Price': 'SD YRP Sales Item Price',
	'SD YRP Sales Piece Sticker Print': 'SD YRP Sales Piece Sticker Print',
	'SD YRP Sewing Plan': 'SD YRP Sewing Plan',
	'SD YRP Sewing Plan Entry Detail': 'SD YRP Sewing Plan Entry Detail',
	'SD YRP Sewing Plan Input Type': 'SD YRP Sewing Plan Input Type',
	'SD YRP Shortened Link': 'SD YRP Shortened Link',
	'SD YRP Signature': 'SD YRP Signature',
	'YRP Supplier': 'YRP Supplier',
	'YRP Tax Slab': 'YRP Tax Slab',
	'SD YRP Telegram Approval Request': 'SD YRP Telegram Approval Request',
	'SD YRP Telegram Approval Settings': 'SD YRP Telegram Approval Settings',
	'YRP Terms and Condition': 'YRP Terms and Condition',
	'YRP UOM': 'YRP UOM',
	'YRP Vendor Bill Delivery Person': 'YRP Vendor Bill Delivery Person',
	"Vendor Bill Tracking": 'YRP Bill Tracking',
	'SD YRP WO Recut': 'SD YRP WO Recut',
	'YRP Work Order': 'YRP Work Order',
}

EXPECTED_EMPTY_DOCTYPES = {
	'SD YRP Item Lead Time',
	'SD YRP P and L Document',
	'SD YRP Purchase Order Log',
	'SD YRP WO Recut',
}

SAFE_ZERO_ARGUMENT_READ_METHODS = (
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.can_approve_grammage",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.can_change_approval_grammage",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot.check_enabled_po",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_product_image.sd_yrp_product_image.get_image_list",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_sales_piece_sticker_print.sd_yrp_sales_piece_sticker_print.get_print_format",
	"essdee_yrp.ipd_ui.get_approval_roles",
	"essdee_yrp.ipd_ui.get_ipd_item_group",
	"essdee_yrp.time_and_action.tracking.get_t_and_a_report_data",
	"essdee_yrp.time_and_action.tracking.get_t_and_a_review_report_data",
	"yrp.stock.api.get_stock_dimensions_for_ui",
	"yrp.whatsapp_notification.get_enabled_whatsapp_doctypes",
	"yrp.yrp.api.ui_config.get_my_ui_config",
	"yrp.yrp.api.ui_config.get_my_ui_overrides",
	"yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.get_rework_output_received_types",
	"yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_close_permission",
)

EXPECTED_NON_METHOD_REFERENCES = {
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_box_sticker_print.sd_yrp_box_sticker_print",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_panel_movement.sd_yrp_cut_panel_movement",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_essdee_quality_inspection.sd_yrp_essdee_quality_inspection",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch.sd_yrp_finishing_plan_dispatch",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_item_conversion.sd_yrp_item_conversion.",
	"essdee_yrp.essdee_yrp.doctype.sd_yrp_stock_summary.sd_yrp_stock_summary.",
	"essdee_yrp.mrp_stock",
	"yrp.yrp.doctype.yrp_item.yrp_item.",
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
	('YRP Production Order', "before_cancel"): "PPO-00194-2",
	# The latest packing WO has a submitted dispatch and is intentionally not
	# cancellable. Exercise the on-cancel handlers with a migrated packing WO
	# whose generated Finishing Plan has no downstream dispatch instead.
	('YRP Work Order', "on_cancel"): "WO-2627-00478",
	('YRP Work Order Correction', "before_submit"): "WOC-2026-00001",
}

DOC_EVENT_FILTERS = {
	# Approved IPDs intentionally reject before_validate/validate mutations.
	# Use a real draft migration sample when exercising the handler inventory.
	'YRP Item Production Detail': {"approval_status": ["!=", "Approved"]},
	# Stale draft Stock Entries can legitimately retain a CPM that was later
	# linked elsewhere. The handler inventory uses an unrelated entry; the CPM
	# rejection and lifecycle are covered by the cutting integration matrix.
	'YRP Stock Entry': {"cut_panel_movement": ["is", "not set"]},
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
							if doctype == 'YRP Production Order' and event == "before_submit":
								frappe.set_user("emp+ansil@essdee.fit")
							try:
								frappe.get_attr(handler)(doc, event)
							except frappe.ValidationError:
								# This inventory intentionally invokes lifecycle hooks on
								# existing live documents. A dependency/idempotency guard is
								# successful execution; compatibility failures such as
								# TypeError/AttributeError must still escape and fail the gate.
								pass
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
		item = frappe.get_all('YRP Item', pluck="name", limit=1)[0]
		work_order = frappe.db.sql(
			"""
			SELECT wo.name
			FROM `tabYRP Work Order` wo
			INNER JOIN `tabYRP Work Order Calculated Item` item ON item.parent = wo.name
			WHERE wo.docstatus = 1
			  AND wo.open_status = 'Open'
			  AND COALESCE(wo.is_rework, 0) = 0
			  AND item.quantity > 0
			ORDER BY wo.modified DESC
			LIMIT 1
			""",
		)[0][0]
		work_order_doc = frappe.get_doc('YRP Work Order', work_order)
		calculated_item = next(
			row for row in work_order_doc.work_order_calculated_items if row.quantity > 0
		)

		samples = (
			frappe.get_doc(
				{
					"doctype": 'SD YRP Item Lead Time',
					"item_name": item,
					"lead_time": 1,
				}
			),
			frappe.get_doc(
				{
					"doctype": 'SD YRP P and L Document',
					"against": 'YRP Item',
					"against_id": item,
					"comments": "Runtime acceptance sample",
				}
			),
			frappe.get_doc(
				{
					"doctype": 'SD YRP Purchase Order Log',
					"type": "Runtime Acceptance",
					"reason": "Rollback-safe lifecycle sample",
				}
			),
			frappe.get_doc(
				{
					"doctype": 'SD YRP WO Recut',
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
		cutting_plan = frappe.get_doc('SD YRP Cutting Plan', "CP-2608-00006")
		lot = cutting_plan.lot

		get_daily_production_summary_report(
			from_date="2099-01-01",
			to_date="2099-01-02",
		)
		multiccr = get_multiccr(lot_list=json.dumps(["F1024-54"]))
		self.assertIn("data", multiccr)

		calls = (
			(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_cloth_accessories",
				{"cutting_plan": cutting_plan.name},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.get_select_attributes",
				{"cutting_plan": cutting_plan.name},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.calculate_parts",
				{"cutting_plan": cutting_plan.name},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_marker.sd_yrp_cutting_marker.get_primary_and_bundle_detail",
				{
					"lot": lot,
					"selected_value": "Machine",
					"panels": [],
					"grp_panels": [],
				},
			),
			(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan.sd_yrp_finishing_plan.get_primary_values",
				{"lot": lot},
			),
		)
		for method, kwargs in calls:
			with self.subTest(method=method):
				frappe.get_attr(method)(**kwargs)
