"""Title-aware Link search for the /web SPA.

The SPA's `searchLink` originally queried only the `name` (ID) column
(`frappe.client.get_list` with `name like %txt%`). That breaks for doctypes whose
human-readable label lives in a separate field — e.g. yrp's `Item` is autonamed
`Item-.#####` (so `name` = "Item-00012") while the descriptive name is in
`name1` ("Greige Yarn"). Typing "Greige" matched nothing.

`link_search` mirrors what the Frappe Desk link search does: match the typed text
against `name` AND the doctype's title / search fields, and return both the `name`
(the value a Link stores) and a `label` (what to show the user). It is
meta-driven — it auto-detects the title field from the doctype meta plus a few
yrp/Frappe conventions (`name1`, `item_name`, `<doctype>_name`, `title`) — so it
needs no per-doctype configuration and degrades to a plain name search when there
is no title field.
"""

import json

import frappe
from yrp.attribute_links import value as _attribute_value

# Conventional human-name field names probed for the LABEL when a doctype has no
# explicit title_field (checked against meta.has_field, so unknowns are safe).
# These name a record for a human; `label` was dropped (too generic to be a title).
_LABEL_GUESSES = ("name1", "item_name", "title", "full_name")


def _label_field(meta):
	"""The single best field to DISPLAY as the human label, or None → use `name`.

	Label candidates are ONLY real "title" fields: the doctype's title_field, the
	`<doctype>_name` convention (supplier_name, …), then a few human-name guesses.
	`search_fields` are deliberately EXCLUDED here — they broaden matching (below)
	but are often not labels: e.g. Goods Received Note's first search field is
	`against_id`, so using it as the label made every GRN show the WO/PO it was
	received against, which read as "the picker is listing Work Orders, not GRNs".
	When no title field exists, the record's own `name` (e.g. GRN-2026-00008) is
	the correct, identifiable label.
	"""
	cand = []
	if meta.title_field:
		cand.append(meta.title_field)
	cand.append(frappe.scrub(meta.name) + "_name")  # supplier_name, customer_name, …
	cand += list(_LABEL_GUESSES)
	for f in cand:
		if f and f != "name" and meta.has_field(f):
			return f
	return None


def _match_fields(meta, label_field):
	"""Fields (besides name) to match the typed txt against — the label field plus
	the doctype's search_fields, so a record is still findable by its searchable
	attributes (a GRN by its supplier / item / source WO) even though those don't
	label it. De-duplicated; only real fields; never `name`."""
	cand = []
	if label_field:
		cand.append(label_field)
	if meta.search_fields:
		cand += [f.strip() for f in meta.search_fields.split(",") if f.strip()]
	seen, out = set(), []
	for f in cand:
		if f and f not in seen and f != "name" and meta.has_field(f):
			seen.add(f)
			out.append(f)
	return out


@frappe.whitelist()
def link_search(doctype, txt="", filters=None, page_length=20, match_visible_only=False):
	"""Search `doctype` by name + title/search fields. Returns [{name, label}].

	`filters` (AND) narrow the result set (e.g. attribute_name for Item Attribute
	Value). List-filter pickers set ``match_visible_only`` so typed text is matched
	only against values shown in the menu (name/title); this prevents a Lot search
	for ``TE`` from returning unrelated-looking IDs merely because their hidden
	Item search field contains ``Vest``. Form links retain Frappe-style matching
	against configured search fields. The `label` is the doctype's human title
	field when it has one, else the `name`.
	"""
	if not doctype:
		return []
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except (TypeError, ValueError):
			filters = {}
	filters = filters or {}
	if doctype == "Item Attribute Value":
		return _search_item_attribute_values(txt, filters, page_length)

	meta = frappe.get_meta(doctype)
	label_field = _label_field(meta)
	match_fields = _match_fields(meta, label_field)
	if match_visible_only:
		match_fields = [label_field] if label_field else []
	txt = (txt or "").strip()

	# Fetch name + the label field (when there is a distinct human title).
	fields = ["name"] + ([label_field] if label_field else [])

	# Empty txt → return the top page_length records (Frappe-desk parity): honor
	# the AND `filters` only, no OR text matching, sorted by modified desc. A
	# non-empty txt adds the OR-across name + match fields below.
	or_filters = None
	if txt:
		like = f"%{txt}%"
		or_filters = [["name", "like", like]] + [[f, "like", like] for f in match_fields]

	try:
		page_len = int(page_length or 20)
	except (TypeError, ValueError):
		page_len = 20
	rows = frappe.get_list(
		doctype,
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		limit_page_length=page_len,
		order_by="modified desc",
	)
	out = []
	for r in rows:
		label = (r.get(label_field) if label_field else None) or r["name"]
		out.append({"name": r["name"], "label": label})
	return out


@frappe.whitelist()
def linked_document_search(
	doctype,
	link_doctype,
	link_name,
	txt="",
	page_length=20,
):
	"""Search Address/Contact records linked to one selected document.

	Addresses and Contacts are connected through Dynamic Link child rows, so a
	regular Link filter cannot express the Desk query.  Resolve the relationship
	server-side, then intersect it through ``get_list`` so normal read permission
	and user permissions still apply to the returned records.
	"""
	if doctype not in {"Address", "Contact"} or not link_doctype or not link_name:
		return []
	if not frappe.has_permission(doctype, ptype="read") or not frappe.has_permission(
		link_doctype, ptype="read"
	):
		return []

	linked_names = frappe.get_all(
		"Dynamic Link",
		filters={
			"parenttype": doctype,
			"link_doctype": link_doctype,
			"link_name": link_name,
		},
		pluck="parent",
		limit_page_length=0,
	)
	linked_names = list(dict.fromkeys(linked_names))
	if not linked_names:
		return []

	meta = frappe.get_meta(doctype)
	label_field = _label_field(meta)
	match_fields = _match_fields(meta, label_field)
	text = (txt or "").strip()
	or_filters = None
	if text:
		like = f"%{text}%"
		or_filters = [["name", "like", like]] + [
			[fieldname, "like", like] for fieldname in match_fields
		]
	try:
		page_len = max(1, int(page_length or 20))
	except (TypeError, ValueError):
		page_len = 20
	rows = frappe.get_list(
		doctype,
		filters={"name": ["in", linked_names]},
		or_filters=or_filters,
		fields=["name"] + ([label_field] if label_field else []),
		limit_page_length=page_len,
		order_by="modified desc",
	)
	return [
		{
			"name": row.name,
			"label": (row.get(label_field) if label_field else None) or row.name,
		}
		for row in rows
	]


def _search_item_attribute_values(txt, filters, page_length):
	"""Expose ERPNext's child-table attribute values as picker values.

	YRP business fields store the selected value as Data, while the canonical
	values now live under the standard Item Attribute document. Keeping this
	adapter in the search boundary lets existing form components use the same
	``[{name, label}]`` contract without pretending the child rows are standalone
	linkable documents.
	"""
	attribute = filters.get("attribute_name") or filters.get("parent")
	if not attribute or not frappe.db.exists("Item Attribute", attribute):
		return []
	frappe.get_doc("Item Attribute", attribute).check_permission("read")
	try:
		page_len = max(1, int(page_length or 20))
	except (TypeError, ValueError):
		page_len = 20
	needle = (txt or "").strip().casefold()
	values = [
		_attribute_value(row.attribute_value)
		for row in frappe.get_all(
			"Item Attribute Value",
			filters={
				"parent": attribute,
				"parenttype": "Item Attribute",
				"parentfield": "item_attribute_values",
			},
			fields=["attribute_value", "idx"],
			order_by="idx asc",
		)
		if _attribute_value(row.attribute_value)
		and (not needle or needle in _attribute_value(row.attribute_value).casefold())
	]
	return [{"name": value, "label": value} for value in values[:page_len]]
