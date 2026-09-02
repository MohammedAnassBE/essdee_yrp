"""Essdee Delivery Challan guardrails for CPM-prepared drafts."""

import frappe
from frappe import _
from frappe.utils import flt

from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import DeliveryChallan


def strip_unselected_cpm_items(doc):
	"""Keep a CPM transaction limited to the quantities selected in that CPM.

	Base Delivery Challan intentionally retains zero rows in an ordinary draft so
	the operator can edit the complete Work Order matrix later. A CPM draft is
	different: its allowed scope is already frozen by the submitted movement.
	Persisting the editor's generated zero-size placeholders also stores numeric
	zero in Link fields such as ``ref_doctype``, which makes a saved draft fail to
	reload with ``DocType 0 not found``. Remove only those CPM-only placeholders;
	ordinary base-YRP Delivery Challans retain their normal behaviour.
	"""
	if not doc.get("cut_panel_movement"):
		return
	doc.set(
		"items",
		[
			row
			for row in (doc.get("items") or [])
			if flt(row.get("qty") or row.get("delivered_quantity")) > 0
		],
	)


def strip_generated_invalid_zero_placeholders(doc):
	"""Drop zero matrix cells whose generated Link values are numeric zero.

	Base Delivery Challan deliberately preserves ordinary zero rows while a draft
	is editable, then removes them on submit. Preserve that contract for genuine
	Work Order rows. The grouped editor can additionally expand primary-attribute
	values that have no Work Order deliverable; those placeholders carry numeric
	``0`` in Link fields and make the saved draft fail to reload with
	``DocType 0 not found``. They are not selectable business rows and can be
	removed without losing the operator's zeroed, valid deliverables.
	"""
	invalid_zero_links = {0, "0"}
	doc.set(
		"items",
		[
			row
			for row in (doc.get("items") or [])
			if not (
				flt(row.get("qty") or row.get("delivered_quantity")) <= 0
				and (
					row.get("ref_doctype") in invalid_zero_links
					or row.get("ref_docname") in invalid_zero_links
				)
			)
		],
	)


class EssdeeDeliveryChallan(DeliveryChallan):
	def set_missing_values(self):
		"""Keep the operator-selected DC source authoritative.

		Base YRP uses the Work Order delivery location as a convenient source
		fallback. Essdee stock can be issued from a different floor location and
		warehouse for each DC, so an empty source must remain empty and fail the
		mandatory-field gate instead of being silently replaced during Save.
		"""
		# Two specialized Essdee services create and submit their own DCs without
		# using the ordinary Desk form. They already carry an explicit source
		# location and retain base's unique-warehouse resolution. The manual Desk
		# contract applies to every other DC, including CPM-prepared drafts.
		if self.get("from_finishing") or self.get("cutting_bulk_lay_sheet"):
			return super().set_missing_values()

		from_location = self.get("from_location")
		from_warehouse = self.get("from_warehouse")
		super().set_missing_values()
		self.from_location = from_location
		self.from_warehouse = from_warehouse

	def validate_items(self):
		"""Allow an Essdee DC to record an in-place dispatch.

		Cutting may issue stock against a Work Order without moving it out of the
		machine-cutting location. The DC must still update its business lineage,
		pending quantities, Cutting projections, and paired stock audit entries.
		Keep every base item/quantity validation; remove only the different-
		warehouse restriction for Essdee.
		"""
		if not (self.get("items") or self.get("correction_items")):
			frappe.throw(_("At least one deliverable or correction item is required."))

		check_qty = self.docstatus == 1
		for row in (self.get("items") or []) + (self.get("correction_items") or []):
			if not row.item_variant:
				frappe.throw(_("Row {0}: Item Variant is required.").format(row.idx))
			if check_qty and flt(row.delivered_quantity or row.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))

	def onload(self):
		# Sanitize in memory before base grouping so historical/in-flight drafts
		# that contain numeric-zero Link values can render and be submitted.
		strip_generated_invalid_zero_placeholders(self)
		strip_unselected_cpm_items(self)
		result = super().onload()
		if self.docstatus == 0:
			# Draft reloads group their persisted children again, so apply the same
			# zero-pending excess adapter used by both new-document API routes.
			from essdee_yrp.work_order_actions import _enable_zero_pending_excess_in_editor

			self.set_onload(
				"item_details",
				_enable_zero_pending_excess_in_editor(
					self.get_onload().get("item_details") or []
				),
			)
		return result

	def before_validate(self):
		super().before_validate()
		# Base sync intentionally keeps zero matrix cells for ordinary drafts.
		# Remove invalid generated placeholders, then apply the narrower CPM
		# contract after that sync and before persistence.
		strip_generated_invalid_zero_placeholders(self)
		strip_unselected_cpm_items(self)
