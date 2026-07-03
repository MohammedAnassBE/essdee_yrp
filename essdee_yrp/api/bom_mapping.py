"""Create / configure Item BOM Attribute Mapping docs from the /web IPD surface.

`BOMMappingEditor.vue` and `IPDConfigView.openMapping` drive the standalone
(non-submittable) **Item BOM Attribute Mapping** doctype, which the IPD engine
reads in "Mode B" to resolve per-variant BOM quantities. The editor builds its
grid columns from the mapping's own `item_attributes` / `bom_item_attributes`
child tables — so those MUST be populated when the mapping is created, or the
grid renders empty ("no item-side attributes to map").

This mirrors production_api's
`item_production_detail.ItemProductionDetail.update_mapping_values`
(essdee_production/.../item_production_detail.py:214-239), which on creating a
mapping for an attribute-mapped BOM row sets:

    item_attributes      = [{attribute: <IPD packing attribute>}]   # item-side driver
    bom_item_attributes  = [{attribute: a} for a in BOM_item.attributes]  # all bom attrs

yrp's IPD has no `packing_attribute`; its analog single item-side driver is
`primary_item_attribute`. yrp's mapping doctype also dropped production_api's
`item_production_detail` link field, so we don't set it — the owning IPD is
recovered (when needed) via the Item BOM child row that back-links the mapping.

Permission model: these run as standalone whitelisted endpoints reachable by any
logged-in /web user, so — unlike production_api, which calls update_mapping_values
from inside the already-permission-gated IPD controller save — we DO NOT pass
`ignore_permissions`. Standard "Item BOM Attribute Mapping" create/write perms
apply (same roles as the sibling editor api/item_attribute.py: System Manager,
Item Master Manager, Production Planner, Merch User). `flags.ignore_validate` is
still set (as the reference does) — that only skips the *values-completeness*
check on a freshly-seeded doc with no `values` yet; it does not bypass perms.
"""

import frappe
from frappe import _


def _bom_item_attribute_rows(bom_item):
	"""[{attribute: a}] for every attribute on the BOM (consumed) Item.

	Mirror production_api: `for item in frappe.get_cached_doc("Item", bom.item).attributes`.
	"""
	if not bom_item:
		return []
	item_doc = frappe.get_cached_doc("Item", bom_item)
	return [{"attribute": a.attribute} for a in (item_doc.attributes or [])]


def _seed_columns(doc, primary_attribute, bom_item):
	"""Populate the mapping's attribute child tables in place (no save).

	item-side = the single primary/packing attribute; bom-side = all bom item
	attributes. Leaves `values` untouched. Throws if the BOM item has no
	attributes (an attribute-mapped BOM row is meaningless without them — better
	a clear message than a dead-end "nothing to map" grid).
	"""
	bom_rows = _bom_item_attribute_rows(bom_item)
	if not bom_rows:
		frappe.throw(
			_("BOM Item {0} has no attributes — it can't be attribute-mapped.").format(bom_item)
		)
	doc.set("item_attributes", [{"attribute": primary_attribute}])
	doc.set("bom_item_attributes", bom_rows)


@frappe.whitelist()
def create_mapping(ipd, bom_item, bom_row=None):
	"""Create an Item BOM Attribute Mapping for an attribute-mapped BOM row.

	`ipd` is the owning Item Production Detail name (gives us `item` +
	`primary_item_attribute`); `bom_item` is the consumed Item; `bom_row` is the
	Item BOM child-row name to back-link (optional). Returns the mapping name.

	Idempotent + transactional: if `bom_row` already links a mapping, that name
	is returned without creating a duplicate; otherwise the insert AND the
	back-link write happen in this one request, so a failure rolls both back
	(no orphaned, never-linked mapping). Faithful port of production_api's
	update_mapping_values create branch.
	"""
	if not ipd:
		frappe.throw(_("IPD is required"))
	if not bom_item:
		frappe.throw(_("BOM Item is required"))

	# The back-link below writes into the IPD's own Item BOM child row, so the
	# caller must hold write on the parent IPD (frappe.db.set_value on a child
	# row would otherwise bypass the parent's permission gate entirely).
	frappe.get_doc("Item Production Detail", ipd).check_permission("write")

	# Idempotency: never create a second mapping for a row that already has one.
	# Also verify the row actually belongs to THIS IPD's item_bom table — a
	# forged bom_row must not re-point another document's row.
	if bom_row:
		row_meta = frappe.db.get_value(
			"Item BOM", bom_row, ["attribute_mapping", "parent", "parenttype"], as_dict=True
		)
		if not row_meta:
			frappe.throw(_("Item BOM row {0} not found").format(bom_row))
		if row_meta.parenttype != "Item Production Detail" or row_meta.parent != ipd:
			frappe.throw(_("Item BOM row {0} does not belong to IPD {1}").format(bom_row, ipd))
		if row_meta.attribute_mapping:
			return row_meta.attribute_mapping

	ipd_doc = frappe.get_cached_doc("Item Production Detail", ipd)
	primary = ipd_doc.primary_item_attribute
	if not primary:
		frappe.throw(
			_("Set a Primary Item Attribute on the IPD before configuring an attribute-mapped BOM.")
		)

	doc = frappe.new_doc("Item BOM Attribute Mapping")
	doc.item = ipd_doc.item
	doc.bom_item = bom_item
	_seed_columns(doc, primary, bom_item)
	doc.flags.ignore_validate = True
	doc.insert()

	# Back-link inside the same transaction so create + link are atomic.
	if bom_row:
		frappe.db.set_value("Item BOM", bom_row, "attribute_mapping", doc.name)
	return doc.name


def _owning_ipd_primary(mapping_name):
	"""Best-effort: the primary attribute of the IPD whose Item BOM row links
	this mapping. Returns the attribute name or None.
	"""
	rows = frappe.get_all(
		"Item BOM",
		filters={"attribute_mapping": mapping_name, "parenttype": "Item Production Detail"},
		fields=["parent"],
		limit=1,
	)
	if not rows:
		return None
	return frappe.db.get_value("Item Production Detail", rows[0].parent, "primary_item_attribute")


@frappe.whitelist()
def configure_columns(mapping):
	"""Heal an existing mapping whose attribute columns were never populated.

	Idempotent: if `item_attributes` already has rows, returns unchanged. Else
	derives item-side = owning IPD's primary attribute, bom-side = bom item's
	attributes, and saves. Used by the editor's empty-state "Configure columns"
	action so a mapping created before this fix (or in Desk without columns)
	becomes usable in /web without a Desk visit.
	"""
	if not mapping:
		frappe.throw(_("Mapping is required"))
	doc = frappe.get_doc("Item BOM Attribute Mapping", mapping)
	if doc.item_attributes:
		return {"name": doc.name, "changed": False}

	primary = _owning_ipd_primary(mapping)
	if not primary:
		frappe.throw(
			_(
				"Cannot determine the item-side attribute — no IPD links this mapping, "
				"or its Primary Item Attribute is unset. Open the IPD and set a Primary "
				"Item Attribute first."
			)
		)
	if not doc.bom_item:
		frappe.throw(_("This mapping has no BOM Item set."))

	_seed_columns(doc, primary, doc.bom_item)
	doc.flags.ignore_validate = True
	doc.save()
	return {"name": doc.name, "changed": True}
