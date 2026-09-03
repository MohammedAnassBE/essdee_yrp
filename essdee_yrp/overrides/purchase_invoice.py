"""Purchase Invoice controller for Essdee grouped commercial rates."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import flt
from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import PurchaseInvoice

from essdee_yrp.erp import is_purchase_invoice_sync_enabled
from essdee_yrp.erp_purchase_invoice import cancel_erp_invoice, create_erp_invoice
from essdee_yrp.purchase_invoice import (
	LEGACY_RATE_SOURCE,
	MODERN_RATE_SOURCE,
	VALUE_TOLERANCE,
	build_legacy_work_order_invoice_payload,
	build_purchase_order_invoice_payload,
	build_verification_details,
	build_work_order_invoice_payload,
	project_purchase_order_items,
)

PROJECTED_AGAINST = {'YRP Purchase Order', 'YRP Work Order'}


class EssdeePurchaseInvoice(PurchaseInvoice):
	def onload(self):
		super().onload()
		if self.against == 'YRP Work Order' and self.get("pi_work_order_billed_details"):
			self.set_onload(
				"item_details",
				build_verification_details(self.get("pi_work_order_billed_details")),
			)
		self.set_onload(
			"erp_purchase_invoice_sync_enabled",
			is_purchase_invoice_sync_enabled(),
		)

	def before_validate(self):
		self._validate_legacy_projection_inputs()
		if self.get("essdee_rate_table_source") == LEGACY_RATE_SOURCE and (
			self.is_new()
			or frappe.db.get_value(
				'YRP Purchase Invoice', self.name, "essdee_rate_table_source"
			) != LEGACY_RATE_SOURCE
		):
			frappe.throw(_("Legacy Purchase Invoice rate data is migration-owned."))
		if self.against == 'YRP Work Order' and self.get("essdee_rate_table_source") in {
			MODERN_RATE_SOURCE,
			LEGACY_RATE_SOURCE,
		}:
			self._rebuild_essdee_work_order_items()
		elif self.against == 'YRP Purchase Order' and self.get(
			"essdee_rate_table_source"
		) in {MODERN_RATE_SOURCE, LEGACY_RATE_SOURCE}:
			self._rebuild_essdee_purchase_order_items()
		super().before_validate()

	def validate(self):
		self._reset_changed_commercial_approval()
		super().validate()
		if self.against in PROJECTED_AGAINST and self.get("essdee_rate_table_source") in {
			MODERN_RATE_SOURCE,
			LEGACY_RATE_SOURCE,
		}:
			self._validate_commercial_total()
			self.total_quantity = sum(flt(row.qty) for row in self.get("essdee_items") or [])

	def before_submit(self):
		if self.against in PROJECTED_AGAINST and self.get("essdee_rate_table_source") not in {
			MODERN_RATE_SOURCE,
			LEGACY_RATE_SOURCE,
		}:
			frappe.throw(_("Fetch GRN into Grouped Items before submitting this invoice."))
		super().before_submit()
		create_erp_invoice(self)

	def before_cancel(self):
		super().before_cancel()
		cancel_erp_invoice(self)

	def _rebuild_essdee_work_order_items(self):
		if self.get("essdee_rate_table_source") == LEGACY_RATE_SOURCE:
			payload = build_legacy_work_order_invoice_payload(self)
			if payload["unlinked"]:
				frappe.throw(_("Fetch GRN again before saving this migrated invoice."))
			self.set("items", payload["items"])
			self.allow_to_change_rate = 1
			self.total_quantity = payload["total_quantity"]
			return

		grns = [row.grn for row in self.get("grn") or [] if row.grn]
		posted_rows = list(self.get("essdee_items") or [])
		posted_keys = [row.group_key for row in posted_rows if row.group_key]
		if len(posted_keys) != len(posted_rows) or len(set(posted_keys)) != len(posted_keys):
			frappe.throw(_("Process Items are stale. Fetch GRN again before saving."))
		final_rates = {row.group_key: row.rate for row in posted_rows}
		expense_heads = {row.group_key: row.expense_head for row in posted_rows}
		payload = build_work_order_invoice_payload(
			grns,
			supplier=self.supplier,
			purchase_invoice=None if self.is_new() else self.name,
			final_rates=final_rates,
			expense_heads=expense_heads,
		)
		expected_keys = {row["group_key"] for row in payload["commercial_items"]}
		if set(posted_keys) != expected_keys:
			frappe.throw(_("Selected GRNs changed. Fetch GRN again before saving."))

		self.set("items", payload["items"])
		self.set("essdee_items", payload["commercial_items"])
		self.set("pi_work_order_billed_details", payload["wo_items"])
		self.allow_to_change_rate = payload["allow_to_change_rate"]
		self.total_quantity = payload["total_quantity"]

	def _rebuild_essdee_purchase_order_items(self):
		posted_rows = list(self.get("essdee_items") or [])
		posted_keys = [row.group_key for row in posted_rows if row.group_key]
		if len(posted_keys) != len(posted_rows) or len(set(posted_keys)) != len(posted_keys):
			frappe.throw(_("Grouped Items are stale. Fetch GRN again before saving."))
		if any(flt(row.rate) < 0 for row in posted_rows):
			frappe.throw(_("Final Purchase Invoice rate cannot be negative."))
		final_rates = {row.group_key: row.rate for row in posted_rows}
		expense_heads = {row.group_key: row.expense_head for row in posted_rows}

		if self.get("essdee_rate_table_source") == LEGACY_RATE_SOURCE:
			before = self.get_doc_before_save()
			if not before:
				frappe.throw(_("Legacy Purchase Invoice rate data is migration-owned."))
			items, commercial_items = project_purchase_order_items(
				before.get("items") or [],
				final_rates=final_rates,
				expense_heads=expense_heads,
			)
			payload = {
				"items": items,
				"commercial_items": commercial_items,
				"allow_to_change_rate": 1,
				"total_quantity": sum(flt(row["qty"]) for row in commercial_items),
			}
		else:
			grns = [row.grn for row in self.get("grn") or [] if row.grn]
			payload = build_purchase_order_invoice_payload(
				grns,
				supplier=self.supplier,
				purchase_invoice=None if self.is_new() else self.name,
				final_rates=final_rates,
				expense_heads=expense_heads,
			)

		expected_keys = {row["group_key"] for row in payload["commercial_items"]}
		if set(posted_keys) != expected_keys:
			frappe.throw(_("Selected GRNs changed. Fetch GRN again before saving."))
		self.set("items", payload["items"])
		self.set("essdee_items", payload["commercial_items"])
		self.allow_to_change_rate = payload["allow_to_change_rate"]
		self.total_quantity = payload["total_quantity"]

	def _validate_legacy_projection_inputs(self):
		before = self.get_doc_before_save()
		if not before or before.get("essdee_rate_table_source") != LEGACY_RATE_SOURCE:
			return
		if self.against != before.against or self.against not in PROJECTED_AGAINST:
			frappe.throw(_("A migrated invoice cannot change its source document type."))
		if self.get("essdee_rate_table_source") not in {
			LEGACY_RATE_SOURCE,
			MODERN_RATE_SOURCE,
		}:
			frappe.throw(_("Fetch GRN again before changing this migrated invoice."))
		if (
			self.get("essdee_rate_table_source") == LEGACY_RATE_SOURCE
			and _legacy_projection_input_signature(before)
			!= _legacy_projection_input_signature(self)
		):
			frappe.throw(
				_(
					"Only Final Rate can be changed in migrated Grouped Items. "
					"Use Fetch GRN to rebuild the invoice from different GRNs."
				)
			)

	def _validate_commercial_total(self):
		for row in self.get("essdee_items") or []:
			row.qty = flt(row.qty)
			row.source_rate = flt(row.source_rate)
			row.rate = flt(row.rate)
			row.amount = row.qty * row.rate
		commercial_total = sum(flt(row.amount) for row in self.get("essdee_items") or [])
		if abs(commercial_total - flt(self.total)) > VALUE_TOLERANCE:
			frappe.throw(
				_(
					"Grouped Items total {0} does not match the valuation item total {1}."
				).format(flt(commercial_total, 2), flt(self.total, 2))
			)

	def _reset_changed_commercial_approval(self):
		before = self.get_doc_before_save()
		if not before or not self.get("approved_by"):
			return
		if _commercial_signature(before) == _commercial_signature(self):
			return
		self.approved_by = None
		self.senior_merch_approved_by = None
		self.set("purchase_invoice_wo_approval_details", [])
		self.status = "Draft"


def _commercial_signature(doc):
	grns = sorted(row.grn for row in doc.get("grn") or [] if row.grn)
	rates = sorted(
		(row.group_key or "", round(flt(row.rate), 6))
		for row in doc.get("essdee_items") or []
	)
	return json.dumps([grns, rates], separators=(",", ":"))


def _legacy_projection_input_signature(doc):
	commercial = [
		(
			row.idx,
			row.group_key or "",
			row.item or "",
			row.lot or "",
			row.item_group or "",
			row.expense_head or "",
			round(flt(row.qty), 9),
			row.uom or "",
			round(flt(row.source_rate), 9),
			row.tax or "",
		)
		for row in doc.get("essdee_items") or []
	]
	grns = [(row.idx, row.grn or "") for row in doc.get("grn") or []]
	billed = [
		(
			row.idx,
			row.work_order or "",
			row.item_variant or "",
			round(flt(row.quantity), 9),
			round(flt(row.total_delivered), 9),
			round(flt(row.total_received), 9),
			round(flt(row.billed), 9),
			_normalized_json(row.get("set_combination")),
			row.get("essdee_group_key") or "",
		)
		for row in doc.get("pi_work_order_billed_details") or []
	]
	return (doc.supplier or "", commercial, grns, billed)


def _normalized_json(value):
	if not value:
		return ""
	try:
		parsed = frappe.parse_json(value) if isinstance(value, str) else value
		return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
	except (TypeError, ValueError):
		return str(value)
