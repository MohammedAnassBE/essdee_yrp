from collections import defaultdict
from functools import cached_property

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.attribute_values import get_mapping_values

from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import (
	get_colour_attribute,
	get_dia_attribute,
)
from essdee_yrp.merch import lot_process_rules as rules
from essdee_yrp.planning.reports import production_quantities as quantities

ORDER_FIELDS = [
	"name",
	"status",
	"docstatus",
	"supplier",
	"supplier_name",
	"process_name",
	"item",
	"includes_packing",
	"creation",
	"wo_date",
]
WORK_ORDER = "YRP Work Order"


def movement_documents(order_names):
	"""Submitted DCs and GRNs of these Work Orders (permission-aware)."""
	if not order_names:
		return [], []
	dcs = frappe.get_list(
		"YRP Delivery Challan",
		filters={"work_order": ["in", order_names], "docstatus": 1},
		fields=["name", "work_order", "posting_date", "supplier", "supplier_name", "total_delivered_qty"],
		order_by="posting_date asc, name asc",
		limit_page_length=0,
	)
	grns = frappe.get_list(
		"YRP Goods Received Note",
		filters={"against": WORK_ORDER, "against_id": ["in", order_names], "docstatus": 1},
		fields=[
			"name",
			"against_id",
			"posting_date",
			"supplier",
			"supplier_name",
			"total_received_quantity",
			"is_return",
			"packing_calculation_version",
		],
		order_by="posting_date asc, name asc",
		limit_page_length=0,
	)
	return dcs, grns


def movement_dates(dcs, grns):
	"""{work order: (first DC date, last GRN date)} from document posting dates."""
	first, last = {}, {}
	for row in dcs:
		first[row["work_order"]] = min(filter(None, [first.get(row["work_order"]), row["posting_date"]]))
	for row in grns:
		if not cint(row.get("is_return")):
			last[row["against_id"]] = max(filter(None, [last.get(row["against_id"]), row["posting_date"]]))
	return {name: (first.get(name), last.get(name)) for name in {*first, *last}}


class LotFlowData:
	"""Batched, read-only data behind a Merch Lot process flow."""

	def __init__(self, lot):
		self.doc = frappe.get_doc("SD YRP Lot", lot)
		self.doc.check_permission("read")
		self.ipd = (
			frappe.get_cached_doc("YRP Item Production Detail", self.doc.production_detail)
			if self.doc.production_detail
			else None
		)

	@cached_property
	def orders(self):
		return frappe.get_list(
			WORK_ORDER,
			filters={"lot": self.doc.name, "is_rework": 0, "docstatus": ["!=", 2]},
			fields=ORDER_FIELDS,
			order_by="creation asc",
			limit_page_length=0,
		)

	@cached_property
	def cloth_items(self):
		return [row.cloth_item for row in self.doc.get("lot_fabric_details") or [] if row.cloth_item]

	@cached_property
	def item_orders(self):
		return [order for order in self.orders if order["item"] == self.doc.item]

	@cached_property
	def submitted(self):
		return [order["name"] for order in self.orders if cint(order["docstatus"]) == 1]

	@cached_property
	def documents(self):
		return movement_documents([order["name"] for order in self.orders])

	@cached_property
	def dates(self):
		return movement_dates(*self.documents)

	@cached_property
	def calculated_items(self):
		names = [order["name"] for order in self.item_orders if order["name"] in self.submitted]
		return quantities.child_rows(
			"YRP Work Order Calculated Item",
			names,
			["item_variant", "set_combination", "quantity", "delivered_quantity", "received_qty"],
			WORK_ORDER,
		)

	@cached_property
	def moves(self):
		"""Deliverables and receivables of submitted Work Orders, by parent."""
		result = {"deliverables": defaultdict(list), "receivables": defaultdict(list)}
		for key, doctype in (
			("deliverables", "YRP Work Order Deliverables"),
			("receivables", "YRP Work Order Receivables"),
		):
			for row in quantities.child_rows(
				doctype, self.submitted, ["item_variant", "qty", "pending_quantity", "uom"], WORK_ORDER
			):
				result[key][row["parent"]].append(row)
		return result

	@cached_property
	def groups(self):
		names = list({order["process_name"] for order in self.orders})
		rows = (
			frappe.get_all(
				"YRP Process Details",
				filters={"parent": ["in", names], "parenttype": "YRP Process"},
				fields=["parent", "process_name"],
				order_by="idx asc",
				limit_page_length=0,
			)
			if names
			else []
		)
		groups = defaultdict(list)
		for row in rows:
			groups[row["parent"]].append(row["process_name"])
		return dict(groups)

	@cached_property
	def item_nodes(self):
		if not self.ipd:
			return []
		processes = [row.as_dict() for row in self.ipd.get("ipd_processes") or []]
		return rules.build_item_nodes(
			rules.item_steps(self.ipd.as_dict(), processes), self.item_orders, self.groups
		)

	@cached_property
	def plans(self):
		names = [order["name"] for order in self.orders]
		cutting = (
			frappe.get_list(
				"SD YRP Cutting Plan",
				filters={"work_order": ["in", names], "docstatus": ["!=", 2]},
				fields=["name", "work_order"],
				limit_page_length=0,
			)
			if names
			else []
		)
		finishing = frappe.get_list(
			"SD YRP Finishing Plan",
			filters={"lot": self.doc.name},
			fields=["name", "work_order", "pieces_per_box"],
			limit_page_length=0,
		)
		return {"cutting": {row["work_order"]: row["name"] for row in cutting}, "finishing": finishing}

	@cached_property
	def sizes(self):
		from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
			get_ipd_primary_values,
		)

		return list(get_ipd_primary_values(self.ipd.name) or []) if self.ipd else []

	def attributes(self, variants):
		return quantities.variant_attributes(set(variants))

	def size_of(self, attributes):
		return lambda variant: attributes.get(variant, {}).get(self.ipd.primary_item_attribute, "")

	@cached_property
	def parts(self):
		if not self.ipd or not self.ipd.is_set_item:
			return 1
		mapping = next(
			(
				row.mapping
				for row in self.ipd.get("item_attributes") or []
				if row.attribute == self.ipd.set_item_attribute and row.mapping
			),
			None,
		)
		return len(get_mapping_values(mapping) or []) if mapping else 1

	@cached_property
	def order_rows(self):
		return [
			{
				"item_variant": row.item_variant,
				"set_combination": row.set_combination,
				"quantity": flt(row.quantity),
			}
			for row in self.doc.get("lot_order_details") or []
		]

	def order_pieces(self):
		"""Order pieces per size: Lot Order Detail quantity ÷ set parts."""
		if not self.ipd:
			return {"sizes": [], "values": {}, "total": 0, "parts": 1}
		size_of = self.size_of(self.attributes(row["item_variant"] for row in self.order_rows))
		values = defaultdict(float)
		for row in self.order_rows:
			values[size_of(row["item_variant"])] += row["quantity"] / self.parts
		return {
			"sizes": self.sizes,
			"values": dict(values),
			"total": sum(values.values()),
			"parts": self.parts,
		}

	def cloth_attributes(self):
		return get_colour_attribute(), get_dia_attribute()

	def packing(self, order_names):
		"""OCR packing quantities per size for the lot's packing Work Order."""
		grns = [
			row
			for row in self.documents[1]
			if row["against_id"] in order_names and not cint(row.get("is_return"))
		]
		versions = {row["name"]: row.get("packing_calculation_version") for row in grns}
		grn_items = [
			{**row, "packing_calculation_version": versions[row["parent"]]}
			for row in quantities.child_rows(
				"YRP Goods Received Note Item",
				versions,
				["item_variant", "quantity"],
				"YRP Goods Received Note",
			)
		]
		plans = {row["name"]: row for row in self.plans["finishing"]}
		dispatched = quantities.child_rows(
			"SD YRP Finishing Plan GRN Detail", plans, ["item_variant", "dispatched"], "SD YRP Finishing Plan"
		)
		items = [row for row in self.calculated_items if row["parent"] in order_names]
		size_of = self.size_of(
			self.attributes(row["item_variant"] for row in [*grn_items, *dispatched, *items])
		)
		delivered = defaultdict(float)
		for row in items:
			delivered[size_of(row["item_variant"])] += flt(row["delivered_quantity"])
		return {
			"planned": self.order_pieces()["values"],
			"delivered": dict(delivered),
			"received": rules.packing_pieces(
				grn_items, size_of, self.doc.packing_combo or self.ipd.packing_combo
			),
			"dispatch": rules.dispatch_pieces(dispatched, size_of, self.dispatch_multipliers(plans.values())),
			"finishing_plans": list(plans),
		}

	def dispatch_multipliers(self, plans):
		work_orders = [row["work_order"] for row in plans if row.get("work_order")]
		tracked = (
			set(
				frappe.get_all(
					"YRP Goods Received Note",
					filters={
						"against": WORK_ORDER,
						"against_id": ["in", work_orders],
						"docstatus": 1,
						"is_return": 0,
						"packing_calculation_version": [">=", 1],
					},
					pluck="against_id",
					limit_page_length=0,
				)
			)
			if work_orders
			else set()
		)
		return {
			row["name"]: 1 if row.get("work_order") in tracked else flt(row.get("pieces_per_box"))
			for row in plans
		}

	def dispatches(self):
		plans = [row["name"] for row in self.plans["finishing"]]
		items = (
			frappe.get_all(
				"SD YRP Finishing Plan Dispatch Item",
				filters={"against_id": ["in", plans], "parenttype": "SD YRP Finishing Plan Dispatch"},
				fields=["parent", "against_id"],
				limit_page_length=0,
			)
			if plans
			else []
		)
		plan_of = {row["parent"]: row["against_id"] for row in items}
		rows = (
			frappe.get_list(
				"SD YRP Finishing Plan Dispatch",
				filters={"name": ["in", list(plan_of)], "docstatus": 1},
				fields=["name", "stock_entry", "fp_total_dispatched"],
				limit_page_length=0,
			)
			if plan_of
			else []
		)
		entries = [row["stock_entry"] for row in rows if row.get("stock_entry")]
		dates = (
			dict(
				frappe.get_all(
					"Stock Entry",
					filters={"name": ["in", entries]},
					fields=["name", "posting_date"],
					as_list=True,
				)
			)
			if entries
			else {}
		)
		return [
			{
				"name": row["name"],
				"date": dates.get(row.get("stock_entry")),
				"qty": flt(row.get("fp_total_dispatched")),
				"finishing_plan": plan_of[row["name"]],
			}
			for row in rows
		]


def require_work_order(name):
	rows = frappe.get_list(
		WORK_ORDER,
		filters={"name": name},
		fields=[*ORDER_FIELDS, "lot", "production_detail"],
		limit_page_length=1,
	)
	if not rows:
		frappe.throw(_("You do not have access to Work Order {0}.").format(name), frappe.PermissionError)
	return rows[0]
