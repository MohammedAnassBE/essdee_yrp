import frappe

ITEM_FIELDS = ("item", "item_variant", "fabric_reference_variant")


class ImportBlocked(Exception):
	"""A data condition that stops one doc or lot; reported without a traceback."""


class Precheck:
	"""Report every missing master before anything is written."""

	def __init__(self, importer, docs):
		self.importer = importer
		self.docs = docs
		self.missing = []
		self.variants_to_create = {}

	def run(self):
		self.check_links()
		self.check_items()
		self.check_ipds_and_lots()
		self.check_addresses()
		return self.missing

	def need(self, doctype, name, where):
		if name and not frappe.db.exists(doctype, name):
			self.missing.append(f"{doctype} {name} ({where})")

	def check_links(self):
		fields = {
			"Supplier": ("supplier", "to_supplier", "default_supplier", "from_location", "delivery_location"),
			"Warehouse": ("to_warehouse", "from_warehouse", "default_warehouse", "warehouse"),
			"SD YRP Lot": ("lot",),
			"YRP Process": ("process_name",),
			"UOM": ("uom", "secondary_uom", "stock_uom"),
			"YRP Received Type": ("received_type",),
			"YRP Tax Slab": ("tax_slab",),
		}
		seen = set()
		for kind, docs in self.docs.items():
			for doc in docs:
				for row in [doc, *child_rows(doc)]:
					for doctype, names in fields.items():
						for field in names:
							key = (doctype, row.get(field))
							if row.get(field) and key not in seen:
								seen.add(key)
								self.need(doctype, row[field], f"{kind} {doc['name']}.{field}")

	def check_items(self):
		names = set()
		for docs in self.docs.values():
			for doc in docs:
				for row in [doc, *child_rows(doc)]:
					names |= {row[f] for f in ITEM_FIELDS if row.get(f)}
		for name in sorted(names):
			variant = self.importer.data["variants"].get(name)
			if resolve_item(name, variant):
				continue
			problem = get_variant_problem(variant)
			if problem:
				self.missing.append(f"Item {name} ({problem})")
			else:
				self.variants_to_create[name] = variant

	def check_ipds_and_lots(self):
		from essdee_yrp.api.work_order import _get_work_order_selection_context

		for wo in self.docs["work_orders"]:
			status = frappe.db.get_value(
				"YRP Item Production Detail", wo["production_detail"], "approval_status"
			)
			if status != "Approved":
				self.missing.append(
					f"Approved YRP Item Production Detail {wo['production_detail']} (WO {wo['name']}, status {status})"
				)
				continue
			if not frappe.db.exists("SD YRP Lot", wo["lot"]):
				continue
			context = _get_work_order_selection_context(wo["lot"], wo["process_name"])
			if not any(
				o["item"] == wo["item"] and o["production_detail"] == wo["production_detail"]
				for o in context["options"]
			):
				self.missing.append(
					f"SD YRP Lot {wo['lot']} fabric row {wo['item']} / {wo['production_detail']} (WO {wo['name']})"
				)
		for pc in self.docs["process_costs"]:
			if not pc.get("lot") or not frappe.db.exists("SD YRP Lot", pc["lot"]):
				continue
			context = _get_work_order_selection_context(pc["lot"], pc["process_name"])
			if pc["item"] not in context["item_options"]:
				self.missing.append(
					f"SD YRP Lot {pc['lot']} fabric row for {pc['item']} / {pc['process_name']} (Process Cost {pc['name']})"
				)

	def check_addresses(self):
		for wo in self.docs["work_orders"]:
			for field, party, kind in (
				("supplier_address", "supplier", "Billing"),
				("delivery_address", "delivery_location", "Shipping"),
			):
				if not resolve_address(wo.get(field), wo.get(party), kind, throw=False):
					self.missing.append(f"Address for {wo.get(party)} ({kind}, WO {wo['name']})")
		parties = set()
		for dc in self.docs["delivery_challans"]:
			parties |= {(dc["from_location"], "Shipping"), (dc["supplier"], "Billing")}
		for grn in self.docs["goods_received_notes"]:
			parties |= {(grn["delivery_location"], "Shipping"), (grn["supplier"], "Billing")}
		for party, kind in sorted(parties):
			if not default_address(party, kind, throw=False):
				self.missing.append(f"Default {kind} Address for {party}")


def child_rows(doc):
	return [row for value in doc.values() if isinstance(value, list) for row in value]


def resolve_item(name, variant):
	"""Existing item by name, else the variant with the same template + attributes. Never creates."""
	if frappe.db.exists("Item", name):
		return frappe.db.get_value("Item", name, "name")
	if not variant or not frappe.db.exists("Item", variant["template"]):
		return None
	from yrp.yrp.doctype.yrp_item.yrp_item import _lookup_variant

	return _lookup_variant(variant["template"], variant["attributes"], backfill_tuple=False)


def get_variant_problem(variant):
	"""Why a missing variant cannot be created from its template, or None when it can."""
	if not variant:
		return "not a variant in the dump"
	template = variant["template"]
	if not frappe.db.get_value("Item", template, "has_variants"):
		return f"template {template} not found or has no variants"
	template_attributes = frappe.get_all(
		"Item Variant Attribute", filters={"parent": template, "parenttype": "Item"}, pluck="attribute"
	)
	if set(template_attributes) != set(variant["attributes"]):
		return f"attributes {sorted(variant['attributes'])} do not match template {sorted(template_attributes)}"
	from yrp.yrp.doctype.yrp_item.yrp_item import validate_attribute_value

	for attribute, value in variant["attributes"].items():
		try:
			validate_attribute_value(attribute, value)
		except frappe.ValidationError:
			frappe.clear_messages()
			return f"{attribute} value {value} not found"
	return None


def resolve_address(name, party, kind, throw=True):
	if name and frappe.db.exists("Address", name):
		return frappe.db.get_value("Address", name, "name")
	return default_address(party, kind, throw=throw)


def default_address(party, kind, throw=True):
	"""Same default the Desk form picks (yrp.party_addresses.get_party_address)."""
	from yrp.party_addresses import get_party_address

	address = get_party_address(party, preferred_type=kind) if party else None
	if not address and throw:
		raise ImportBlocked(f"No default {kind} address for {party}")
	return address
