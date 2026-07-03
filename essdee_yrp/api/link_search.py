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
def link_search(doctype, txt="", filters=None, page_length=20):
	"""Search `doctype` by name + title/search fields. Returns [{name, label}].

	`filters` (AND) narrow the result set (e.g. attribute_name for Item Attribute
	Value); the typed `txt` is matched as an OR across name + the match fields. The
	`label` is the doctype's human title field when it has one, else the `name`.
	"""
	if not doctype:
		return []
	if isinstance(filters, str):
		try:
			filters = json.loads(filters)
		except (TypeError, ValueError):
			filters = {}
	filters = filters or {}

	meta = frappe.get_meta(doctype)
	label_field = _label_field(meta)
	match_fields = _match_fields(meta, label_field)
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
