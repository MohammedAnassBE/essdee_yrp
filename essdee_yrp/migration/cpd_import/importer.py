import copy
import json
import os
import re
import traceback
from collections import defaultdict

import frappe
from frappe.utils import cstr, flt

from essdee_yrp.migration.cpd_import.masters import (
	ITEM_FIELDS,
	ImportBlocked,
	Precheck,
	default_address,
	resolve_address,
	resolve_item,
)

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "import_data.json")
MARKER = "CPD import from {old}"
GRN_NOT_FOUND = "GRN not found on this site"
STD_SKIP = {
	"name",
	"idx",
	"docstatus",
	"doctype",
	"naming_series",
	"amended_from",
	"status",
	"workflow_state",
	"approved_by",
	"item_details",
	"correction_item_details",
	"deliverable_details",
	"receivable_details",
}
TARGET = {
	"Process Cost": "YRP Process Cost",
	"Stock Entry": "YRP Stock Entry",
	"Stock Reconciliation": "YRP Stock Reconciliation",
	"Work Order": "YRP Work Order",
	"Delivery Challan": "YRP Delivery Challan",
	"Goods Received Note": "YRP Goods Received Note",
}
SOURCE_KEYS = {
	"Process Cost": "process_costs",
	"Stock Entry": "stock_entries",
	"Stock Reconciliation": "stock_reconciliations",
	"Work Order": "work_orders",
	"Delivery Challan": "delivery_challans",
	"Goods Received Note": "goods_received_notes",
}
ROW_DOCTYPE = {
	"Work Order Deliverables": "YRP Work Order Deliverables",
	"Work Order Receivables": "YRP Work Order Receivables",
}
WORK_ORDER_TABLES = ("deliverables", "receivables")
DATA_FIELDTYPES = {
	"Data",
	"Link",
	"Dynamic Link",
	"Select",
	"Int",
	"Float",
	"Currency",
	"Check",
	"Date",
	"Time",
	"Datetime",
	"Small Text",
	"Text",
	"Long Text",
	"Percent",
	"JSON",
	"Code",
	"Text Editor",
	"Read Only",
}
LOG_KEYS = ("created", "skipped", "failed", "notes")


class Importer:
	"""Import the submitted CPD docs in order; commits per doc / lot only when `commit` is set."""

	def __init__(self, commit, ignore_markers=False):
		if commit and ignore_markers:
			frappe.throw("ignore_markers is only allowed in a dry run")
		frappe.set_user("Administrator")
		with open(DATA_PATH) as handle:
			self.data = json.load(handle)
		self.docs = self.data["docs"]
		self.commit = commit
		self.ignore_markers = ignore_markers
		self.names = defaultdict(dict)
		self.row_map = {}
		self.item_names = {}
		self.log = {key: [] for key in LOG_KEYS}

	def run(self):
		"""Return False when the pre-check fails; nothing is written then.

		Only docs still to import are pre-checked. With `ignore_markers` the pre-check is report-only,
		so every create path still runs and fails on its own.
		"""
		precheck = Precheck(self, self.get_pending_docs())
		missing = precheck.run()
		if missing:
			self.log["failed"].append({"doctype": "Pre-check", "old": "-", "error": "; ".join(missing)})
			if not self.ignore_markers:
				return False
		if not self.create_variants(precheck.variants_to_create):
			return False
		for pc in sorted(self.docs["process_costs"], key=lambda d: d["name"]):
			self.per_doc("Process Cost", pc, self.import_process_cost)
		for kind, doc in self.stock_vouchers():
			importer = self.import_stock_entry if kind == "Stock Entry" else self.import_stock_reconciliation
			self.per_doc(kind, doc, importer)
		for lot, chain in self.lot_chains().items():
			self.import_lot(lot, chain)
		return True

	def create_variants(self, variants):
		"""Create the variants the pre-check found missing from their existing template; all or none."""
		from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant

		state = self.get_state()
		frappe.db.savepoint("cpd_variants")
		old = None
		try:
			for old, variant in sorted(variants.items()):
				new = get_or_create_variant(variant["template"], variant["attributes"])
				self.item_names[old] = new
				self.log["created"].append({"doctype": "Item Variant", "old": old, "new": new})
				print("CREATED", "Item Variant", old, "->", new)
		except Exception as error:
			self.undo("cpd_variants", state)
			for name in variants:
				self.item_names.pop(name, None)
			self.fail("Item Variant", old, error)
			return False
		self.save()
		return True

	def get_pending_docs(self):
		if self.ignore_markers:
			return self.docs
		return {
			key: [doc for doc in self.docs[key] if not self.imported_name(source_doctype, doc["name"])]
			for source_doctype, key in SOURCE_KEYS.items()
		}

	# ---------- markers / name map ----------
	def imported_name(self, source_doctype, old):
		"""Return the submitted target doc carrying this old name's marker."""
		doctype = TARGET[source_doctype]
		name = frappe.db.get_value(
			"Comment",
			{"comment_type": "Info", "reference_doctype": doctype, "content": MARKER.format(old=old)},
			"reference_name",
		)
		if name and frappe.db.get_value(doctype, name, "docstatus") == 1:
			return name
		return None

	def mapped(self, source_doctype, old):
		new = self.names[source_doctype].get(old) or self.imported_name(source_doctype, old)
		if not new:
			raise ImportBlocked(f"{source_doctype} {old} has no imported target doc")
		return new

	def already(self, source_doctype, source):
		"""Skip a doc that is already imported; `ignore_markers` re-imports it (links still resolve)."""
		existing = None if self.ignore_markers else self.imported_name(source_doctype, source["name"])
		if not existing:
			return False
		self.names[source_doctype][source["name"]] = existing
		if source_doctype == "Work Order":
			self.map_rows(frappe.get_doc(TARGET[source_doctype], existing), source, WORK_ORDER_TABLES)
		self.log["skipped"].append(
			{"doctype": source_doctype, "old": source["name"], "new": existing, "reason": "already imported"}
		)
		return True

	def created(self, source_doctype, old, doc):
		doc.add_comment("Info", MARKER.format(old=old))
		self.names[source_doctype][old] = doc.name
		self.log["created"].append({"doctype": source_doctype, "old": old, "new": doc.name})
		print("CREATED", source_doctype, old, "->", doc.name)

	# ---------- transactions ----------
	def get_state(self):
		lengths = {key: len(self.log[key]) for key in LOG_KEYS if key != "failed"}
		return lengths, copy.deepcopy(self.names), dict(self.row_map)

	def undo(self, savepoint, state):
		"""Roll back one doc or lot and its log entries; return the rolled back created rows."""
		frappe.db.rollback(save_point=savepoint)
		if self.commit:
			frappe.db.rollback()
		lengths, self.names, self.row_map = state
		rolled = self.log["created"][lengths["created"] :]
		for key, length in lengths.items():
			del self.log[key][length:]
		return rolled

	def save(self):
		if self.commit:
			frappe.db.commit()  # nosemgrep: one doc or lot per transaction

	def per_doc(self, source_doctype, source, importer):
		if self.already(source_doctype, source):
			return
		state = self.get_state()
		frappe.db.savepoint("cpd_doc")
		try:
			result = importer(source)
		except Exception as error:
			self.undo("cpd_doc", state)
			self.fail(source_doctype, source["name"], error)
			return
		self.save()
		if result:
			self.log["skipped"].append({"doctype": source_doctype, "old": source["name"], "reason": result})

	def import_lot(self, lot, chain):
		steps = [("Work Order", d, self.import_work_order) for d in chain["wo"]]
		steps += [("Delivery Challan", d, self.import_delivery_challan) for d in chain["dc"]]
		steps += [("Goods Received Note", d, self.import_goods_received_note) for d in chain["grn"]]
		savepoint = "cpd_lot_" + re.sub(r"\W", "_", lot)
		state = self.get_state()
		frappe.db.savepoint(savepoint)
		current = (steps[0][0], steps[0][1]["name"])
		try:
			for source_doctype, source, importer in steps:
				current = (source_doctype, source["name"])
				if not self.already(source_doctype, source):
					importer(source)
		except Exception as error:
			rolled = self.undo(savepoint, state)
			self.fail(*current, error)
			self.log["failed"][-1]["lot"] = lot
			self.log["failed"][-1]["rolled_back"] = [
				f"{r['doctype']} {r['old']} (was {r['new']})" for r in rolled
			]
			return
		self.save()

	def fail(self, source_doctype, old, error):
		message = cstr(error) or error.__class__.__name__
		self.log["failed"].append({"doctype": source_doctype, "old": old, "error": message[:800]})
		print("FAILED", source_doctype, old, message[:300])
		if not isinstance(error, ImportBlocked):
			print(traceback.format_exc()[-3000:])

	# ---------- generic copy helpers ----------
	def copy_fields(self, doctype, source, exclude=()):
		meta = frappe.get_meta(doctype)
		out = {}
		for key, value in source.items():
			if key in STD_SKIP or key in exclude or value in (None, ""):
				continue
			field = meta.get_field(key)
			if field and field.fieldtype in DATA_FIELDTYPES:
				out[key] = self.item(value) if key in ITEM_FIELDS else value
		return out

	def item(self, name):
		if name not in self.item_names:
			self.item_names[name] = resolve_item(name, self.data["variants"].get(name))
		if not self.item_names[name]:
			raise ImportBlocked(f"Item {name} not found on target")
		return self.item_names[name]

	def new_doc(self, source_doctype, source, exclude=(), tables=()):
		doc = frappe.new_doc(TARGET[source_doctype])
		doc.update(self.copy_fields(doc.doctype, source, exclude))
		for table, child_exclude in tables:
			child = doc.meta.get_field(table).options
			for row in sorted(source.get(table) or [], key=lambda r: r.get("idx") or 0):
				doc.append(table, self.copy_fields(child, row, child_exclude))
		return doc

	# ---------- Process Cost ----------
	def import_process_cost(self, source):
		from frappe.model.workflow import apply_workflow

		doc = self.new_doc(
			"Process Cost", source, exclude=("is_expired",), tables=[("process_cost_values", ())]
		)
		doc.insert()
		apply_workflow(doc, "Submit")
		doc = apply_workflow(doc, "Approve")
		if doc.docstatus != 1 or doc.workflow_state != "Approved":
			raise ImportBlocked(
				f"Process Cost {doc.name} is {doc.workflow_state}/{doc.docstatus} after approval"
			)
		if source.get("approved_by") and frappe.db.exists("User", source["approved_by"]):
			doc.db_set("approved_by", source["approved_by"], update_modified=False)
		self.created("Process Cost", source["name"], doc)

	# ---------- Stock Entry / Reconciliation ----------
	def stock_vouchers(self):
		rows = [("Stock Entry", d) for d in self.docs["stock_entries"]]
		rows += [("Stock Reconciliation", d) for d in self.docs["stock_reconciliations"]]
		return sorted(rows, key=lambda r: (r[1]["posting_date"], r[1]["posting_time"]))

	def import_stock_entry(self, source):
		decision, grn = self.get_mrp_grn_decision(source)
		if decision == "skip":
			self.log["notes"].append(
				f"Stock Entry {source['name']} skipped: MRP {grn} stock is still on target (no issue out)"
			)
			return f"duplicate of MRP {grn} (stock still on target; GRN has no essdee_yrp_stock_entry / material issue)"
		doc = self.new_doc("Stock Entry", source, exclude=("total_amount",), tables=[("items", ())])
		doc.edit_posting_date_and_time = 1
		doc.insert()
		doc.submit()
		self.created("Stock Entry", source["name"], doc)
		if decision == "pair":
			frappe.db.set_value(
				"YRP Goods Received Note", grn, "essdee_yrp_stock_entry", doc.name, update_modified=False
			)
			self.log["notes"].append(
				f"Stock Entry {source['name']} -> {doc.name} imported as receiving half of MRP {grn}; "
				f"{grn}.essdee_yrp_stock_entry set"
			)
		return None

	def get_grn_not_found_rows(self):
		"""Source Stock Entries whose cited MRP GRN is absent here; they are imported as the only receipt."""
		rows = []
		for source in self.docs["stock_entries"]:
			grn = get_cited_grn(source)
			if grn and not frappe.db.exists("YRP Goods Received Note", grn):
				new = self.names["Stock Entry"].get(source["name"]) or "not imported"
				rows.append([source["name"], grn, new, GRN_NOT_FOUND])
		return rows

	def get_mrp_grn_decision(self, source):
		grn = get_cited_grn(source)
		if not grn:
			return "import", None
		row = frappe.db.get_value(
			"YRP Goods Received Note",
			grn,
			[
				"docstatus",
				"essdee_yrp_stock_entry_created",
				"mrp_material_issue_ref",
				"essdee_yrp_stock_entry",
			],
			as_dict=True,
		)
		if not row:
			return "no-grn", grn
		if row.docstatus != 1:
			raise ImportBlocked(f"MRP {grn} is docstatus {row.docstatus}; decide manually")
		if row.essdee_yrp_stock_entry_created or row.mrp_material_issue_ref:
			return "pair", grn
		return "skip", grn

	def import_stock_reconciliation(self, source):
		doc = self.new_doc("Stock Reconciliation", source, tables=[("items", ())])
		doc.edit_posting_date_and_time = 1
		doc.insert()
		doc.submit()
		self.created("Stock Reconciliation", source["name"], doc)

	# ---------- Lot chains ----------
	def lot_chains(self):
		chains = defaultdict(lambda: {"wo": [], "dc": [], "grn": []})
		wo_lot = {}
		for wo in self.docs["work_orders"]:
			chains[wo["lot"]]["wo"].append(wo)
			wo_lot[wo["name"]] = wo["lot"]
		for dc in self.docs["delivery_challans"]:
			chains[wo_lot.get(dc["work_order"], dc.get("lot"))]["dc"].append(dc)
		for grn in self.docs["goods_received_notes"]:
			chains[wo_lot.get(grn["against_id"], grn.get("lot"))]["grn"].append(grn)
		for chain in chains.values():
			chain["wo"].sort(key=lambda d: (d["wo_date"], d["name"]))
			for key in ("dc", "grn"):
				chain[key].sort(key=lambda d: (d["posting_date"], d["posting_time"]))
		return dict(sorted(chains.items()))

	# ---------- Work Order ----------
	def import_work_order(self, source):
		row_skip = (
			"pending_quantity",
			"stock_update",
			"process_cost",
			"cost",
			"total_cost",
			"source_grn",
			"source_grn_item",
		)
		doc = self.new_doc(
			"Work Order",
			source,
			exclude=(
				"process_cost",
				"is_delivered",
				"total_quantity",
				"supplier_address",
				"delivery_address",
				"supplier_address_details",
				"delivery_address_details",
				"cloth_execution_version",
			),
			tables=[("deliverables", row_skip), ("receivables", row_skip), ("work_order_tracking_logs", ())],
		)
		doc.edit_wo_date = 1
		doc.supplier_address = resolve_address(
			source.get("supplier_address"), source.get("supplier"), "Billing"
		)
		doc.delivery_address = resolve_address(
			source.get("delivery_address"), source.get("delivery_location"), "Shipping"
		)
		doc.insert()
		self.map_rows(doc, source, WORK_ORDER_TABLES)
		doc.submit()
		expected = self.mapped("Process Cost", source["process_cost"]) if source.get("process_cost") else None
		if expected and doc.process_cost != expected:
			raise ImportBlocked(
				f"WO {source['name']} resolved Process Cost {doc.process_cost}, expected {expected}"
			)
		bad_rows = [r.idx for r in doc.receivables if expected and r.process_cost != expected]
		if bad_rows:
			raise ImportBlocked(
				f"WO {source['name']} receivable rows {bad_rows} lack Process Cost {expected}"
			)
		self.created("Work Order", source["name"], doc)

	def map_rows(self, doc, source, tables):
		for table in tables:
			new_rows = sorted(doc.get(table), key=lambda r: r.idx)
			old_rows = sorted(source.get(table) or [], key=lambda r: r.get("idx") or 0)
			if len(new_rows) != len(old_rows):
				raise ImportBlocked(
					f"{doc.doctype} {doc.name} {table}: {len(new_rows)} rows for {len(old_rows)} source rows"
				)
			for new, old in zip(new_rows, old_rows, strict=True):
				if (
					new.item_variant != self.item(old["item_variant"])
					or abs(flt(new.qty) - flt(old["qty"])) > 0.0001
				):
					raise ImportBlocked(f"{table} row {old['name']} does not match {doc.name} row {new.name}")
				self.row_map[old["name"]] = new.name

	# ---------- Delivery Challan / GRN ----------
	def import_delivery_challan(self, source):
		doc = self.new_doc(
			"Delivery Challan",
			source,
			exclude=(
				"work_order",
				"total_delivered_qty",
				"stock_value",
				"total_value",
				"from_address",
				"supplier_address",
			),
		)
		doc.work_order = self.mapped("Work Order", source["work_order"])
		doc.edit_posting_date_and_time = 1
		doc.from_address = default_address(doc.from_location, "Shipping")
		doc.supplier_address = default_address(doc.supplier, "Billing")
		doc.item_details = self.remap_item_details(source["item_details"])
		doc.insert()
		doc.submit()
		self.check_quantities(doc, source, "qty")
		self.created("Delivery Challan", source["name"], doc)

	def import_goods_received_note(self, source):
		doc = self.new_doc(
			"Goods Received Note",
			source,
			exclude=("against", "against_id", "delivery_challan", "total_received_quantity", "total"),
		)
		doc.against = "YRP Work Order"
		doc.against_id = self.mapped("Work Order", source["against_id"])
		if source.get("delivery_challan"):
			doc.delivery_challan = self.mapped("Delivery Challan", source["delivery_challan"])
		doc.edit_posting_date_and_time = 1
		doc.delivery_address = default_address(doc.delivery_location, "Shipping")
		doc.supplier_address = default_address(doc.supplier, "Billing")
		doc.delivery_date = source["posting_date"]
		doc.item_details = self.remap_item_details(source["item_details"])
		doc.insert()
		doc.submit()
		self.check_quantities(doc, source, "quantity")
		self.created("Goods Received Note", source["name"], doc)

	def remap_item_details(self, raw):
		groups = json.loads(raw or "[]")
		for group in groups:
			for entry in group.get("items") or []:
				self.remap_refs(entry)
				for values in (entry.get("values") or {}).values():
					self.remap_refs(values or {})
		return json.dumps(groups)

	def remap_refs(self, holder):
		if holder.get("ref_doctype") in ROW_DOCTYPE:
			holder["ref_doctype"] = ROW_DOCTYPE[holder["ref_doctype"]]
		old = holder.get("ref_docname")
		if old:
			if old not in self.row_map:
				raise ImportBlocked(f"item_details ref_docname {old} has no new Work Order row")
			holder["ref_docname"] = self.row_map[old]

	def check_quantities(self, doc, source, qty_field):
		def totals(rows, item_of):
			out = defaultdict(float)
			for row in rows:
				if flt(row[qty_field]) > 0:
					out[item_of(row)] += flt(row[qty_field])
			return {k: round(v, 3) for k, v in out.items()}

		new = totals([r.as_dict() for r in doc.items], lambda r: r["item_variant"])
		old = totals(source["items"], lambda r: self.item(r["item_variant"]))
		if new != old:
			raise ImportBlocked(f"{doc.doctype} {doc.name} item qty {new} != source {old}")


def get_cited_grn(source):
	match = re.search(r"GRN-\d{4}-\d+", source.get("comments") or "")
	return source.get("source_grn") or (match.group(0) if match else None)
