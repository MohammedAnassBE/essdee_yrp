"""Sewing Plan lifecycle owned by the Essdee Work Order workflow."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt


def on_work_order_submit(doc, method=None):
	if not _should_have_sewing_plan(doc):
		return
	create_or_get_sewing_plan(doc)


def before_work_order_cancel(doc, method=None):
	plan = frappe.db.get_value('SD YRP Sewing Plan', {"work_order": doc.name}, "name")
	if not plan:
		return
	entry = frappe.db.get_value(
		'SD YRP Sewing Plan Entry Detail', {"sewing_plan": plan}, "name"
	)
	if entry:
		frappe.throw(
			_(
				"Cannot cancel Work Order {0} because Sewing Plan entry {1} exists."
			).format(frappe.bold(doc.name), frappe.bold(entry))
		)


def on_work_order_cancel(doc, method=None):
	plan = frappe.db.get_value('SD YRP Sewing Plan', {"work_order": doc.name}, "name")
	if plan:
		frappe.delete_doc('SD YRP Sewing Plan', plan, ignore_permissions=True)


@frappe.whitelist()
def create_sewing_plan(work_order: str) -> str | None:
	"""Permission-aware manual repair endpoint; normal creation is on submit."""

	work_order_doc = frappe.get_doc('YRP Work Order', work_order)
	work_order_doc.check_permission("read")
	frappe.has_permission('SD YRP Sewing Plan', "create", throw=True)
	if work_order_doc.docstatus != 1:
		frappe.throw(_("Work Order {0} must be submitted.").format(work_order))
	if not _should_have_sewing_plan(work_order_doc):
		return None
	return create_or_get_sewing_plan(work_order_doc)


def create_or_get_sewing_plan(work_order) -> str:
	work_order = (
		frappe.get_doc('YRP Work Order', work_order)
		if isinstance(work_order, str)
		else work_order
	)
	existing = frappe.db.get_value(
		'SD YRP Sewing Plan', {"work_order": work_order.name}, "name"
	)
	if existing:
		return existing

	rows = _order_rows(work_order)
	if not rows:
		frappe.throw(
			_("Work Order {0} has no calculated items for its Sewing Plan.").format(
				frappe.bold(work_order.name)
			)
		)

	plan = frappe.new_doc('SD YRP Sewing Plan')
	plan.naming_series = _default_naming_series()
	plan.work_order = work_order.name
	plan.lot = work_order.lot
	plan.item = work_order.item
	plan.supplier = work_order.supplier
	plan.supplier_address = work_order.supplier_address
	plan.set("sewing_plan_order_details", rows)
	plan.insert(ignore_permissions=True)
	return plan.name


def _should_have_sewing_plan(work_order) -> bool:
	if work_order.get("is_rework"):
		return False
	if not cint(work_order.get("is_internal_unit")):
		return False
	if not cint(
		frappe.db.get_value('YRP Supplier', work_order.supplier, "apply_sewing_plan")
	):
		return False

	sewing_process = frappe.db.get_single_value(
		'SD YRP MRP Settings', "finishing_inward_process"
	)
	if not sewing_process or not work_order.process_name:
		return False
	if work_order.process_name == sewing_process:
		return True
	if not cint(
		frappe.db.get_value('YRP Process', work_order.process_name, "is_group")
	):
		return False
	return bool(
		frappe.db.exists(
			'YRP Process Details',
			{
				"parent": work_order.process_name,
				"parenttype": 'YRP Process',
				"process_name": sewing_process,
			},
		)
	)


def _order_rows(work_order) -> list[dict]:
	rows = []
	for row in work_order.get("work_order_calculated_items") or []:
		if not row.item_variant:
			continue
		rows.append(
			{
				"item_variant": row.item_variant,
				"set_combination": row.set_combination,
				# Zero-size rows are deliberate: Sewing data-entry and reports use
				# the complete variant grid even when this Work Order ordered none
				# of one size.
				"quantity": flt(row.quantity),
			}
		)
	return rows


def _default_naming_series() -> str:
	field = frappe.get_meta('SD YRP Sewing Plan').get_field("naming_series")
	options = [line.strip() for line in (field.options or "").splitlines() if line.strip()]
	default = (field.default or "").strip()
	series = default or (options[0] if options else "")
	if not series:
		frappe.throw(_("Configure a Naming Series for Sewing Plan."))
	return series
