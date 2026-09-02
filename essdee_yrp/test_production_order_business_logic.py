import json

import frappe
from frappe import _dict
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate
from yrp.utils import get_variant_attr_details

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import get_item_details as get_lot_item_details
from essdee_yrp.production_order_workflow import (
	PPO_DRAFT_STATUS,
	PPO_REQUEST_STATUS,
	STATUS_APPROVAL_REQUIRED_STATUSES,
	TRANSFER_TARGET_STATUSES,
	_validate_ppo_approval_state,
	format_request_timestamp,
	get_order_editor_context,
	get_quantity_ratio_changes,
	get_price_update_context,
	onload,
	update_production_order_date,
	validate_size_quantities,
)


class TestProductionOrderBusinessLogic(IntegrationTestCase):
	def _submitted_order(self):
		name = frappe.get_all(
			'YRP Production Order',
			filters={"docstatus": 1, "status": "Open"},
			pluck="name",
			limit=1,
		)[0]
		return frappe.get_doc('YRP Production Order', name)

	def test_workflow_endpoints_are_authenticated(self):
		methods = (
			"get_price_update_context",
			"get_production_order_details",
			"update_price",
			"update_production_order_date",
			"request_ppo_approval",
			"request_ppo_changes",
			"approve_ppo",
			"update_quantity_and_ratio",
			"approve_quantity_and_ratio",
			"create_lot",
			"link_lot",
			"change_status",
			"approve_status_change",
			"transfer_quantity_to_ppo",
			"approve_quantity_transfer",
		)
		for method in methods:
			function = frappe.get_attr(
				f"essdee_yrp.production_order_workflow.{method}"
			)
			self.assertIn(function, frappe.whitelisted, method)
			self.assertNotIn(function, frappe.guest_methods, method)

	def test_onload_restores_production_workflow_context(self):
		doc = self._submitted_order()
		onload(doc)
		context = doc.get("__onload") or {}
		self.assertIn("can_manage_production_order", context)
		self.assertIn("items", context)
		self.assertIn("ordered_details", context)
		self.assertIn("linked_lots", context)

	def test_price_context_matches_current_order_sizes(self):
		doc = self._submitted_order()
		context = get_price_update_context(doc.name)
		self.assertEqual(set(context), {"primary_values", "items", "lots"})
		self.assertEqual(set(context["primary_values"]), set(context["items"]))

	def test_order_editor_context_exposes_essdee_ratio_contract(self):
		doc = self._submitted_order()
		context = get_order_editor_context(doc.item, doc.name)
		self.assertEqual(context["item"], doc.item)
		self.assertTrue(context["primary_attribute"])
		self.assertEqual(set(context["primary_values"]), set(context["items"]))
		for row in context["items"].values():
			self.assertTrue({"qty", "ratio", "mrp", "wholesale", "retail"} <= set(row))

	def test_base_entry_expansion_keeps_essdee_ratio_and_prices(self):
		source = self._submitted_order()
		source_row = source.production_order_details[0]
		attributes = (
			json.loads(source_row.attributes_json)
			if source_row.attributes_json
			else get_variant_attr_details(source_row.item_variant)
		)
		doc = frappe.new_doc('YRP Production Order')
		doc.item = source.item
		doc.delivery_date = source.delivery_date
		doc.posting_date = source.posting_date
		doc.dont_deliver_after = source.dont_deliver_after
		doc.item_details = frappe.as_json(
			[
				{
					"item": source.item,
					"entries": [
						{
							"attributes": attributes,
							"qty": 17,
							"ratio": 3,
							"mrp": 199,
							"wholesale": 101,
							"retail": 151,
						}
					],
				}
			]
		)

		doc.run_method("before_validate")

		self.assertEqual(len(doc.production_order_details), 1)
		row = doc.production_order_details[0]
		self.assertEqual(row.quantity, 17)
		self.assertEqual(row.ratio, 3)
		self.assertEqual(row.mrp, 199)
		self.assertEqual(row.wholesale_price, 101)
		self.assertEqual(row.retail_price, 151)

	def test_request_timestamp_is_valid_frappe_datetime_without_microseconds(self):
		self.assertEqual(
			format_request_timestamp("2026-08-20 10:24:28.918273"),
			"2026-08-20 10:24:28",
		)
		self.assertNotIn(".", format_request_timestamp())

	def test_lot_entry_receives_ratio_stored_on_production_order(self):
		linked = frappe.get_all(
			'SD YRP Lot',
			filters={
				"production_order": ["is", "set"],
				"production_detail": ["is", "set"],
			},
			fields=["production_order", "production_detail"],
			limit=1,
		)[0]
		doc = frappe.get_doc('YRP Production Order', linked.production_order)
		row = doc.production_order_details[0]
		original_ratio = row.ratio
		try:
			frappe.db.set_value(
				'YRP Production Order Detail',
				row.name,
				"ratio",
				7,
				update_modified=False,
			)
			context = get_lot_item_details(
				doc.item,
				production_detail=linked.production_detail,
				ppo=doc.name,
			)
		finally:
			frappe.db.set_value(
				'YRP Production Order Detail',
				row.name,
				"ratio",
				original_ratio,
				update_modified=False,
			)

		ppo_entry = context["items"][0]
		size = get_variant_attr_details(row.item_variant)[ppo_entry["primary_attribute"]]
		self.assertEqual(ppo_entry["values"][size]["ratio"], 7)

	def test_submitted_date_change_requires_tracked_endpoint(self):
		doc = self._submitted_order()
		doc.dont_deliver_after = add_days(doc.dont_deliver_after, 1)
		with self.assertRaises(frappe.ValidationError):
			doc.save()

		doc.reload()
		new_date = add_days(
			max(getdate(doc.delivery_date), getdate(doc.dont_deliver_after)), 1
		)
		result = update_production_order_date(
			doc.name,
			"Don't Deliver After",
			new_date,
			"Automated parity verification",
		)
		self.assertEqual(getdate(result["new_date"]), getdate(new_date))
		doc.reload()
		self.assertEqual(getdate(doc.dont_deliver_after), getdate(new_date))
		self.assertEqual(
			doc.date_change_history[-1].reason,
			"Automated parity verification",
		)

	def test_price_request_actions_are_authenticated(self):
		for method in ("approve_ppo_price_request", "reject_ppo_price_request"):
			function = frappe.get_attr(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_ppo_price_request."
				f"sd_yrp_ppo_price_request.{method}"
			)
			self.assertIn(function, frappe.whitelisted)
			self.assertNotIn(function, frappe.guest_methods)

	def test_approval_status_cannot_be_spoofed(self):
		doc = _dict(docstatus=0, status=PPO_REQUEST_STATUS, flags=_dict())
		doc.get_doc_before_save = lambda: _dict(status=PPO_DRAFT_STATUS)
		with self.assertRaises(frappe.ValidationError):
			_validate_ppo_approval_state(doc)

	def test_pending_ppo_request_can_be_edited_without_spoofing_status(self):
		doc = _dict(
			docstatus=0,
			status=PPO_REQUEST_STATUS,
			flags=_dict(),
			production_term="Updated Term",
		)
		doc.get_doc_before_save = lambda: _dict(status=PPO_REQUEST_STATUS)

		_validate_ppo_approval_state(doc)

		self.assertEqual(doc.status, PPO_REQUEST_STATUS)

	def test_quantity_request_calculation_does_not_mutate_rows(self):
		rows = {
			"S": _dict(quantity=10, ratio=1),
			"M": _dict(quantity=20, ratio=2),
		}
		details = get_quantity_ratio_changes(
			rows,
			{"S": 15, "M": 20},
			{"S": 1, "M": 3},
		)
		self.assertEqual(details["qty_old_total"], 30)
		self.assertEqual(details["qty_new_total"], 35)
		self.assertEqual(rows["S"].quantity, 10)
		self.assertEqual(rows["M"].ratio, 2)

	def test_quantity_and_transfer_contracts_match_production(self):
		rows = {"S": _dict(quantity=10, ratio=1)}
		with self.assertRaises(frappe.ValidationError):
			validate_size_quantities({"S": 1.5}, rows)
		with self.assertRaises(frappe.ValidationError):
			validate_size_quantities({"S": -1}, rows)
		self.assertEqual(
			TRANSFER_TARGET_STATUSES,
			["Open", "Item Changed", "Not Processed"],
		)
		self.assertEqual(
			STATUS_APPROVAL_REQUIRED_STATUSES,
			["Item Changed", "Not Processed"],
		)
