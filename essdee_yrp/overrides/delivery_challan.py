"""Essdee Delivery Challan guardrails for CPM-prepared drafts."""

from frappe.utils import flt

from yrp.yrp.doctype.delivery_challan.delivery_challan import DeliveryChallan


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
