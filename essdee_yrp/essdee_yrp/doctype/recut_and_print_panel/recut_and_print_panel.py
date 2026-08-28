# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from yrp.stock.dimensions import get_dimension_fieldnames
from yrp.stock.stock_ledger import make_sl_entries
from yrp.stock.uom import resolve_item_uom
from yrp.stock.utils import get_stock_balance
from yrp.yrp.doctype.delivery_challan.delivery_challan import (
	_get_warehouse_for_supplier,
)
from yrp.yrp.doctype.item.item import get_or_create_variant


class RecutandPrintPanel(Document):
	def before_validate(self):
		self._validate_context()
		self._set_cloth_variants_and_rates()

	def before_submit(self):
		self._update_cutting_plan(multiplier=1)
		make_sl_entries(self._get_stock_ledger_entries())

	def before_cancel(self):
		self.ignore_linked_doctypes = ("Stock Ledger Entry", "Repost Item Valuation")
		self._update_cutting_plan(multiplier=-1)

	def on_cancel(self):
		make_sl_entries(self._get_stock_ledger_entries(cancel=True), cancel=True)

	def _validate_context(self):
		if not self.cutting_plan:
			return
		plan = frappe.get_doc("Cutting Plan", self.cutting_plan)
		plan.check_permission("read")
		if self.lot and plan.lot != self.lot:
			frappe.throw(
				_("Cutting Plan {0} does not belong to Lot {1}.").format(
					plan.name, self.lot
				)
			)

	def _warehouse(self):
		warehouse = _get_warehouse_for_supplier(self.supplier)
		if not warehouse:
			frappe.throw(
				_("Exactly one enabled Warehouse must be linked to Supplier {0}.").format(
					self.supplier
				)
			)
		return warehouse

	def _cloth_templates(self):
		production_detail = frappe.db.get_value("Lot", self.lot, "production_detail")
		if not production_detail:
			frappe.throw(_("Lot {0} has no Item Production Detail.").format(self.lot))
		packing_attribute = frappe.db.get_value(
			"Item Production Detail", production_detail, "packing_attribute"
		)
		cloth_templates = {
			row.name1: row.cloth
			for row in frappe.get_all(
				"Item Production Detail Cloth Detail",
				filters={"parent": production_detail},
				fields=["name1", "cloth"],
			)
		}
		return packing_attribute, cloth_templates

	def _dimension_values(self, row):
		values = {}
		for fieldname in get_dimension_fieldnames():
			value = row.get(fieldname) if row.meta.get_field(fieldname) else None
			if not value and self.meta.get_field(fieldname):
				value = self.get(fieldname)
			if fieldname == "lot" and not value:
				value = self.lot
			if value:
				values[fieldname] = value
		return values

	def _set_cloth_variants_and_rates(self):
		if not self.lot or not self.supplier:
			return
		packing_attribute, cloth_templates = self._cloth_templates()
		warehouse = self._warehouse()
		default_received_type = frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		)
		for row in self.get("recut_and_print_panel_details") or []:
			template = cloth_templates.get(row.cloth_type)
			if not template:
				frappe.throw(
					_("Cloth Type {0} is not configured in the Item Production Detail.").format(
						row.cloth_type
					)
				)
			row.item_variant = get_or_create_variant(
				template,
				{"Dia": row.dia, packing_attribute: row.colour},
			)
			uom = resolve_item_uom(row.item_variant)
			row.uom = uom.uom
			row.stock_uom = uom.stock_uom
			if row.meta.get_field("received_type") and not row.received_type:
				row.received_type = default_received_type
			_balance, row.rate = get_stock_balance(
				row.item_variant,
				warehouse,
				posting_date=self.posting_date,
				posting_time=self.posting_time,
				with_valuation_rate=True,
				**self._dimension_values(row),
			)

	def _update_cutting_plan(self, *, multiplier):
		cloth = {}
		for row in self.get("recut_and_print_panel_details") or []:
			key = (row.colour, row.cloth_type, row.dia)
			cloth[key] = flt(cloth.get(key)) + flt(row.weight)

		plan = frappe.get_doc("Cutting Plan", self.cutting_plan)
		matched = set()
		for row in plan.get("cutting_plan_cloth_details") or []:
			key = (row.colour, row.cloth_type, row.dia)
			if key not in cloth:
				continue
			matched.add(key)
			row.used_weight = flt(row.used_weight) + (multiplier * cloth[key])
			row.balance_weight = flt(row.weight) - flt(row.used_weight)
			if row.balance_weight < -1e-6:
				frappe.throw(
					_("{0} {1}, {2} was used more than the received weight.").format(
						frappe.bold(row.dia),
						frappe.bold(row.colour),
						frappe.bold(row.cloth_type),
					)
				)
		missing = set(cloth) - matched
		if missing:
			colour, cloth_type, dia = next(iter(missing))
			frappe.throw(
				_("No Cutting Plan cloth row exists for {0} / {1} / {2}.").format(
					dia, colour, cloth_type
				)
			)
		plan.save(ignore_permissions=True)

	def _get_stock_ledger_entries(self, *, cancel=False):
		warehouse = self._warehouse()
		entries = []
		for row in self.get("recut_and_print_panel_details") or []:
			is_incoming = bool(cancel)
			entry = {
				"item": row.item_variant,
				"warehouse": warehouse,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"voucher_detail_no": row.name,
				"qty": flt(row.weight) if is_incoming else -flt(row.weight),
				"uom": row.stock_uom,
				"rate": flt(row.rate) if is_incoming else 0,
				"outgoing_rate": 0 if is_incoming else flt(row.rate),
				"is_cancelled": 1 if cancel else 0,
				"posting_date": self.posting_date,
				"posting_time": self.posting_time,
				**self._dimension_values(row),
			}
			entries.append(entry)
		return entries
