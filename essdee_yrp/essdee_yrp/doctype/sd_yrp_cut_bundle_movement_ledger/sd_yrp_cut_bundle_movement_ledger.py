# Copyright (c) 2025, Essdee and contributors
# For license information, please see license.txt

from collections import defaultdict
import json

import frappe
from frappe import _
from frappe.utils import flt, nowdate, nowtime
from frappe.model.document import Document
from yrp.stock.utils import get_combine_datetime
from yrp.yrp.doctype.yrp_item.yrp_item import build_variant_attributes, get_or_create_variant
from yrp.utils import get_variant_attr_details, update_if_string_instance

def _get_tuple_attributes(tuple_data):
	return {data[0]: data[1] for data in tuple_data}


def _normalise_set_combination(value):
	value = update_if_string_instance(value)
	if value in (None, ""):
		return {}
	if not isinstance(value, dict):
		frappe.throw(_("Set Combination must be a JSON object."))
	return value


def _set_combination_key(value):
	return json.dumps(
		_normalise_set_combination(value), sort_keys=True, separators=(",", ":")
	)


def _collapsed_set_combination(value):
	"""Return the F15 business identity used by collapsed-bundle stock.

	Exact cutting rows can retain marker metadata such as ``major_panel`` and
	layout flags. The production_api collapsed flow deliberately keyed stock by
	major colour and optional major part, which is also the combination carried
	by Work Order transaction rows.
	"""
	value = _normalise_set_combination(value)
	return {
		fieldname: value[fieldname]
		for fieldname in ("major_colour", "major_part")
		if value.get(fieldname) is not None
	}


def _collapsed_set_combination_key(value):
	return json.dumps(
		_collapsed_set_combination(value), sort_keys=True, separators=(",", ":")
	)


def _transaction_bundle_quantities(doc, ipd_doc):
	"""Return the physical panel quantities represented by transaction rows.

	Accessories do not have the IPD's stitching attribute and are intentionally
	ignored here: they move through the stock ledger, not the bundle ledger.
	Stock Entry rows do not retain Set Combination, so their quantities are
	aggregated by the three variant attributes only.
	"""
	variant_field = "item" if doc.doctype == 'YRP Stock Entry' else "item_variant"
	quantity_field = {
		'YRP Delivery Challan': "delivered_quantity",
		'YRP Goods Received Note': "quantity",
		'YRP Stock Entry': "qty",
	}.get(doc.doctype)
	if not quantity_field:
		frappe.throw(_("{0} cannot move cut bundles.").format(doc.doctype))

	quantities = defaultdict(float)
	for row in doc.get("items") or []:
		quantity = flt(row.get(quantity_field), 3)
		if quantity <= 0:
			continue
		variant = row.get(variant_field)
		attributes = get_variant_attr_details(variant) if variant else {}
		panel = attributes.get(ipd_doc.stiching_attribute)
		if not panel:
			continue
		size = attributes.get(ipd_doc.primary_item_attribute)
		colour = attributes.get(ipd_doc.packing_attribute)
		if not size or not colour:
			frappe.throw(
				_("Item Variant {0} is missing its bundle Size or Colour attribute.").format(
					variant
				)
			)
		key = (str(size), str(colour), str(panel))
		if doc.doctype != 'YRP Stock Entry':
			key += (_set_combination_key(row.get("set_combination")),)
		quantities[key] += quantity
	return quantities


def _bundle_key(doc, row, grouped_panel, panel):
	key = (
		str(row.get("size")),
		str(row.get(f"{grouped_panel}_colour")),
		str(panel),
	)
	if doc.doctype != 'YRP Stock Entry':
		key += (_set_combination_key(row.get("set_combination")),)
	return key


def _validate_selected_bundle_quantities(required, selected):
	for key in sorted(set(required) | set(selected)):
		required_qty = flt(required.get(key), 3)
		selected_qty = flt(selected.get(key), 3)
		if required_qty == selected_qty:
			continue
		size, colour, panel = key[:3]
		frappe.throw(
			_(
				"{0} / {1} / {2}: transaction quantity {3} does not match "
				"the selected whole-bundle quantity {4}. Select only the bundles "
				"for this transaction, and use another Cut Panel Movement for a later split."
			).format(panel, colour, size, required_qty, selected_qty)
		)


class SDYRPCutBundleMovementLedger(Document):
	def set_posting_datetime(self):
		if not self.posting_date:
			self.posting_date = nowdate()
		if not self.posting_time:
			self.posting_time = nowtime()
		posting_datetime = get_combine_datetime(self.posting_date, self.posting_time)
		self.posting_datetime = posting_datetime

	def update_item_variant(self):
		ipd = frappe.get_value('SD YRP Lot', self.lot, "production_detail")
		if not ipd:
			return
		ipd_fields = ["stiching_in_stage", "primary_item_attribute", "packing_attribute", "stiching_attribute"]
		stich_stage, primary_attr, pack_attr, stich_attr = frappe.get_value('YRP Item Production Detail', ipd, ipd_fields)
		my_attributes = {
			primary_attr: self.size,
			pack_attr: self.colour,
			stich_attr: self.panel,
		}
		attrs = build_variant_attributes(my_attributes, stich_stage, ipd)
		variant = get_or_create_variant(self.item, attrs)
		self.item_variant = variant

	def set_key(self):
		lot_hash = frappe.get_cached_value('SD YRP Lot', self.lot, "lot_hash_value")
		item_hash = frappe.get_cached_value('YRP Item', self.item, "item_hash_value")
		parts = [
			str(lot_hash), str(self.supplier), str(self.lay_no), str(self.bundle_no),
			str(self.shade), str(item_hash), str(self.size), str(self.colour), str(self.panel),
		]
		self.cbm_key = "-".join(parts)

def get_cut_bundle_entry(cpm_doc, doc, target_warehouse, multiplier, cancelled=0):
	x = frappe.json.loads(cpm_doc.cut_panel_movement_json)
	items = []
	supplier = target_warehouse
	ipd, item = frappe.get_value(
		'SD YRP Lot', cpm_doc.lot, ["production_detail", "item"]
	) or (None, None)
	if not ipd or not item:
		frappe.throw(
			_("Lot {0} is missing its Item Production Detail or Item.").format(cpm_doc.lot)
		)
	ipd_doc = frappe.get_cached_doc('YRP Item Production Detail', ipd)
	panel_quantities = {
		row.stiching_attribute_value: flt(row.quantity)
		for row in ipd_doc.get("stiching_item_details") or []
	}
	required = _transaction_bundle_quantities(doc, ipd_doc)
	selected = defaultdict(float)
	for colour in x['data'].keys():
		part = x['data'][colour]['part']
		panels = x['panels'][part] if part else x['panels']
		for row in x['data'][colour]['data']:
			for grouped_panel in panels:
				if not row.get(grouped_panel) or not row.get(grouped_panel+"_moved"):
					continue
				for panel in (value.strip() for value in grouped_panel.split(",") if value.strip()):
					key = _bundle_key(doc, row, grouped_panel, panel)
					if key not in required:
						continue
					if panel not in panel_quantities:
						frappe.throw(
							_("Panel {0} is not configured in {1}.").format(panel, ipd)
						)
					bundle_quantity = flt(row.get(grouped_panel), 3)
					selected[key] += bundle_quantity * panel_quantities[panel]
					items.append({
						"lot": cpm_doc.lot,
						"supplier": supplier,
						"lay_no": row['lay_no'],
						"bundle_no": row['bundle_no'],
						"panel": panel,
						"shade": row['shade'],
						"posting_date": doc.posting_date,
						"posting_time": doc.posting_time,
						"size": row['size'],
						"colour": row[grouped_panel+'_colour'],
						"quantity": bundle_quantity * multiplier,
						"item": item,
						"voucher_type": doc.doctype,
						"voucher_no": doc.name,
						"is_cancelled": cancelled,
						"set_combination": frappe.json.dumps(
							_normalise_set_combination(row.get('set_combination'))
						),
					})
	_validate_selected_bundle_quantities(required, selected)
	collapsed_details = []

	return items, collapsed_details

def make_cut_bundle_ledger(entries, collapsed_entries=[]):
	if len(entries) == 0:
		return
	if entries[0]['is_cancelled']:
		frappe.throw("Can't cancel the documents")
	else:
		for entry in entries:
			previous = get_previous_entry(entry)
			future = get_future_entry(entry)
			if future:
				frappe.throw("Change the date and time to complete Stock Movement")

			if previous:
				entry['quantity_after_transaction'] = entry['quantity'] + previous[0]['quantity_after_transaction']
			else:
				entry['quantity_after_transaction'] = entry['quantity']

			if entry['quantity_after_transaction'] < 0:
				frappe.throw("Stock is not Avaliable in Source")

			make_cut_bundle_entry(entry)

def make_cut_bundle_entry(entry):
	entry['doctype'] = 'SD YRP Cut Bundle Movement Ledger'
	new_doc = frappe.get_doc(entry)
	new_doc.flags.ignore_permissions = 1
	new_doc.set_posting_datetime()
	new_doc.set_key()
	new_doc.submit()

def get_future_entry(entry, collapsed_bundle=0):
	posting_datetime = get_combine_datetime(entry['posting_date'], entry['posting_time'])
	key = get_cbm_key(entry)
	future = frappe.db.sql(
		"""
			SELECT name, quantity_after_transaction, set_combination FROM `tabSD YRP Cut Bundle Movement Ledger`
			WHERE cbm_key = %(key)s AND posting_datetime > %(datetime)s AND is_cancelled = 0 AND is_collapsed = 0
			AND collapsed_bundle = %(collapsed)s AND transformed = 0
			ORDER BY posting_datetime DESC
		""",{
			"key": key,
			"datetime": posting_datetime,
			"collapsed": collapsed_bundle,
		}, as_dict=True
	)
	future = _filter_set_combination(future, entry.get("set_combination"))
	return future if future else None

def get_previous_entry(entry, collapsed_bundle=0):
	posting_datetime = get_combine_datetime(entry['posting_date'], entry['posting_time'])
	key = get_cbm_key(entry)
	previous = frappe.db.sql(
		"""
			SELECT name, quantity_after_transaction, set_combination FROM `tabSD YRP Cut Bundle Movement Ledger`
			WHERE cbm_key = %(key)s AND posting_datetime <= %(datetime)s AND is_cancelled = 0 AND is_collapsed = 0
			AND collapsed_bundle = %(collapsed)s AND transformed = 0
			ORDER BY posting_datetime DESC, creation DESC, name DESC
		""", {
			"key": key,
			"datetime": posting_datetime,
			"collapsed": collapsed_bundle,
		}, as_dict=True
	)
	previous = _filter_set_combination(previous, entry.get("set_combination"))[:1]
	return previous if previous else None

def get_cbm_key(entry):
	lot_hash = frappe.get_cached_value('SD YRP Lot', entry['lot'], "lot_hash_value")
	item_hash = frappe.get_cached_value('YRP Item', entry['item'], "item_hash_value")
	parts = [
		str(lot_hash),
		str(entry['supplier']),
		str(entry['lay_no']),
		str(entry['bundle_no']),
		str(entry['shade']),
		str(item_hash),
		str(entry['size']),
		str(entry['colour']),
		str(entry['panel']),
	]
	cbm_key = "-".join(parts)
	return cbm_key

def cancel_cut_bundle_ledger(entries):
	if len(entries) == 0:
		return
	if entries[0]['is_cancelled'] == 0:
		frappe.throw("Can't create the documents")
	else:
		for entry in entries:
			previous = get_previous_entry(entry)
			future = get_future_entry(entry)
			if previous and not future:
				frappe.db.sql(
					"""
						UPDATE `tabSD YRP Cut Bundle Movement Ledger` SET is_cancelled = 1 WHERE name = %(name)s
					""", {
						"name": previous[0]['name'],
					}
				)
			else:
				frappe.throw("Stock is Not Available")

def _collapsed_lot(doc):
	lot = doc.get("lot")
	if not lot and doc.doctype == 'YRP Stock Entry' and doc.against and doc.against_id:
		lot = frappe.db.get_value(doc.against, doc.against_id, "lot")
	if not lot:
		for row in doc.get("items") or []:
			if row.get("lot"):
				return row.get("lot")
	return lot


def _resolve_stock_entry_set_combination(lot, location, item, attributes, attrs):
	rows = frappe.get_all(
		'SD YRP Cut Bundle Movement Ledger',
		filters={
			"lot": lot,
			"supplier": location,
			"item": item,
			"size": attributes.get(attrs["primary"]),
			"colour": attributes.get(attrs["pack"]),
			"panel": attributes.get(attrs["stich"]),
			"is_cancelled": 0,
			"transformed": 0,
		},
		pluck="set_combination",
	)
	combinations = {
		_collapsed_set_combination_key(value): _collapsed_set_combination(value)
		for value in rows
	}
	if len(combinations) > 1:
		frappe.throw(
			_(
				"Stock Entry cannot identify one Set Combination for {0} / {1} / {2}. "
				"Use a Delivery Challan or separate the combinations first."
			).format(
				attributes.get(attrs["stich"]),
				attributes.get(attrs["pack"]),
				attributes.get(attrs["primary"]),
			)
		)
	return next(iter(combinations.values()), {})


def _collapsed_transaction_rows(doc, lot, source_location, attrs):
	variant_field = "item" if doc.doctype == 'YRP Stock Entry' else "item_variant"
	quantity_field = {
		'YRP Delivery Challan': "delivered_quantity",
		'YRP Goods Received Note': "quantity",
		'YRP Stock Entry': "qty",
	}.get(doc.doctype)
	if not quantity_field:
		frappe.throw(_("{0} cannot move collapsed bundles.").format(doc.doctype))

	movements = {}
	for row in doc.get("items") or []:
		quantity = flt(row.get(quantity_field), 3)
		if quantity <= 0:
			continue
		variant = row.get(variant_field)
		item = frappe.db.get_value('YRP Item Variant', variant, "item")
		dependent_attribute = frappe.db.get_value('YRP Item', item, "dependent_attribute")
		if not dependent_attribute or not check_dependent_stage_variant(
			variant, dependent_attribute, attrs["stich_stage"]
		):
			continue
		attributes = get_variant_attr_details(variant)
		combination = row.get("set_combination")
		if doc.doctype == 'YRP Stock Entry' and not combination:
			combination = _resolve_stock_entry_set_combination(
				lot, source_location, item, attributes, attrs
			)
		combination = _collapsed_set_combination(combination)
		key = (variant, _collapsed_set_combination_key(combination))
		movement = movements.setdefault(
			key,
			frappe._dict(
				variant=variant,
				item=item,
				attributes=attributes,
				set_combination=combination,
				quantity=0,
			),
		)
		movement.quantity += quantity
	return list(movements.values())


def update_collapsed_bundle(doctype, docname, event, non_stich_process=False):
	del non_stich_process
	if event not in {"on_submit", "on_cancel"}:
		frappe.throw(_("Unsupported collapsed-bundle event {0}.").format(event))

	doc = frappe.get_doc(doctype, docname)
	lot = _collapsed_lot(doc)
	if not lot:
		return
	ipd = frappe.db.get_value('SD YRP Lot', lot, "production_detail")
	if not ipd or not frappe.db.exists('SD YRP Cut Bundle Movement Ledger', {"lot": lot}):
		return
	fields = [
		"primary_item_attribute",
		"packing_attribute",
		"stiching_attribute",
		"stiching_in_stage",
		"dependent_attribute",
	]
	primary, packing, stitching, stitching_stage, dependent = frappe.db.get_value(
		'YRP Item Production Detail', ipd, fields
	)
	attrs = {
		"primary": primary,
		"pack": packing,
		"stich": stitching,
		"stich_stage": stitching_stage,
		"stage": dependent,
	}
	from essdee_yrp.cutting.movement import _movement_locations

	from_location, to_location = _movement_locations(doc)
	movements = _collapsed_transaction_rows(doc, lot, from_location, attrs)
	from_opening = {}
	to_opening = {}
	for movement in movements:
		if event == "on_submit":
			from_opening = on_submit_collapsed_bundles(
				doc,
				doctype,
				docname,
				from_location,
				movement.variant,
				movement.set_combination,
				movement.attributes,
				attrs,
				movement.item,
				movement.quantity,
				from_opening,
				lot,
			)
			to_opening = on_submit_collapsed_bundles(
				doc,
				doctype,
				docname,
				to_location,
				movement.variant,
				movement.set_combination,
				movement.attributes,
				attrs,
				movement.item,
				movement.quantity,
				to_opening,
				lot,
				add=True,
			)
		else:
			for location in (from_location, to_location):
				cancel_collapse_bundles(
					doc,
					movement.variant,
					movement.set_combination,
					movement.quantity,
					location,
					movement.attributes,
					attrs,
					movement.item,
					lot,
				)

	for bundle_key, values in from_opening.items():
		create_new_collapsed_bundle(
			bundle_key, values["bundle_qty"], values["qty"], from_location, doc, {}, attrs
		)
	for bundle_key, values in to_opening.items():
		create_new_collapsed_bundle(
			bundle_key, values["bundle_qty"], values["qty"], to_location, doc, {}, attrs
		)

def _mark_exact_bundle_history_collapsed(cbm_doc):
	target_combination = _collapsed_set_combination_key(cbm_doc.set_combination)
	for row in frappe.get_all(
		'SD YRP Cut Bundle Movement Ledger',
		filters={
			"cbm_key": cbm_doc.cbm_key,
			"collapsed_bundle": 0,
			"is_cancelled": 0,
		},
		fields=["name", "set_combination"],
	):
		if _collapsed_set_combination_key(row.set_combination) == target_combination:
			frappe.db.set_value(
				'SD YRP Cut Bundle Movement Ledger',
				row.name,
				"is_collapsed",
				1,
				update_modified=False,
			)


def on_submit_collapsed_bundles(
	doc,
	doctype,
	docname,
	location,
	item_variant,
	set_combination,
	d,
	attrs,
	item,
	quantity,
	bundles_dict,
	lot_value,
	add=False,
):
	set_combination = _collapsed_set_combination(set_combination)
	previous = get_collapsed_previous_cbm_list(
		doc.posting_date,
		doc.posting_time,
		location,
		item_variant,
		lot=lot_value,
		set_combination=set_combination,
	)
	future = get_collapsed_future_cbm_list(
		doc.posting_date,
		doc.posting_time,
		location,
		item_variant,
		limit=False,
		lot=lot_value,
		set_combination=set_combination,
	)
	delta = flt(quantity, 3) * (1 if add else -1)
	if not previous and not future:
		row_panel = d[attrs["stich"]]
		set_combination_list = sorted(set_combination.items())
		set_combination_string = frappe.json.dumps(set_combination_list)
		for bundle in get_latest_cbml_for_variant(
			location,
			lot_value,
			d[attrs["primary"]],
			d[attrs["pack"]],
			row_panel,
			item,
		):
			cbm_doc = frappe.get_doc('SD YRP Cut Bundle Movement Ledger', bundle["name"])
			if _collapsed_set_combination_key(
				cbm_doc.set_combination
			) != _collapsed_set_combination_key(
				set_combination
			):
				continue
			for panel in (value.strip() for value in cbm_doc.panel.split(",") if value.strip()):
				key = "|".join(
					[
						str(cbm_doc.lot),
						str(cbm_doc.item),
						str(cbm_doc.size),
						str(cbm_doc.colour),
						str(panel),
						set_combination_string,
					]
				)
				values = bundles_dict.setdefault(key, {"qty": 0, "bundle_qty": 0})
				values["bundle_qty"] += flt(cbm_doc.quantity_after_transaction)
			_mark_exact_bundle_history_collapsed(cbm_doc)

		key = "|".join(
			[
				str(lot_value),
				str(item),
				str(d[attrs["primary"]]),
				str(d[attrs["pack"]]),
				str(row_panel),
				set_combination_string,
			]
		)
		values = bundles_dict.setdefault(key, {"qty": 0, "bundle_qty": 0})
		values["qty"] += delta
		return bundles_dict

	if not previous:
		frappe.throw(
			_("Move {0} after its first collapsed-bundle transaction.").format(
				item_variant
			)
		)

	new_balance = flt(previous[0]["quantity_after_transaction"], 3) + delta
	if new_balance < 0:
		frappe.throw(
			_("Collapsed-bundle stock is not available for {0} at {1}.").format(
				item_variant, location
			)
		)
	for entry in future:
		future_balance = flt(entry["quantity_after_transaction"], 3) + delta
		if future_balance < 0:
			frappe.throw(
				_("This movement would make a later collapsed-bundle balance negative.")
			)
		update_future_entries_qty_after_transaction(entry["name"], future_balance)
	create_inter_cbml_doc(
		previous[0]["name"],
		doctype,
		docname,
		quantity,
		1 if add else -1,
		doc.posting_date,
		doc.posting_time,
	)
	return bundles_dict


def cancel_collapse_bundles(
	doc, item_variant, set_combination, quantity, location, d, attrs, item, lot_value
):
	del quantity
	entries = get_collapsed_previous_cbm_list(
		"9999-12-31",
		"23:59:59",
		location,
		item_variant,
		limit=False,
		lot=lot_value,
		set_combination=set_combination,
	)
	entries = sorted(
		entries,
		key=lambda row: (row.posting_datetime, row.creation, row.name),
	)
	current_indexes = [
		index
		for index, row in enumerate(entries)
		if row.voucher_type == doc.doctype and row.voucher_no == doc.name
	]
	if not current_indexes:
		return
	current_index = current_indexes[-1]
	current = entries[current_index]
	if current_index < len(entries) - 1:
		later = entries[current_index + 1]
		frappe.throw(
			_("Cancel the later collapsed-bundle movement {0} {1} first.").format(
				later.voucher_type, later.voucher_no
			)
		)
	update_is_cancelled_cbml(current.name)
	if current_index == 0:
		update_uncollapsed(
			location,
			set_combination,
			lot_value,
			d[attrs["primary"]],
			d[attrs["pack"]],
			d[attrs["stich"]],
			item,
		)


def create_new_collapsed_bundle(
	bundle_key, bundle_total_qty, stock_moved_qty, from_location, doc, d, attrs, new=False
):
	del d, new
	lot, item, size, colour, panel, set_combination = bundle_key.split("|")
	set_combination = frappe.json.loads(set_combination)
	ipd = frappe.get_value('SD YRP Lot', lot, "production_detail")
	ipd_doc = frappe.get_doc('YRP Item Production Detail', ipd)
	panel_qty_dict = {}
	for row in ipd_doc.stiching_item_details:
		panel_qty_dict[row.stiching_attribute_value] = row.quantity

	panel_qty = panel_qty_dict[panel]
	stock_moved_qty = flt(stock_moved_qty) / panel_qty
	bundle_qty = flt(bundle_total_qty) + stock_moved_qty

	if bundle_qty < 0:
		frappe.throw(
			_("Collapsed-bundle stock is not available for {0} / {1} / {2}.").format(
				panel, colour, size
			)
		)

	lay_no = bundle_no = 0
	# Let the IPD mapping decide which attributes the stiching stage needs (don't hand-pick keys).
	my_attributes = {
		attrs['primary']: size,
		attrs['pack']: colour,
		attrs['stich']: panel,
	}
	variant = get_or_create_variant(item, build_variant_attributes(my_attributes, attrs['stich_stage'], ipd_doc))
	set_combination = _get_tuple_attributes(set_combination)
	d = {
		"lot" : lot,
		"item" : item,
		"item_variant": variant,
		"size" : size,
		"colour" : colour,
		"panel" : panel,
		"lay_no" : lay_no,
		"bundle_no" : bundle_no,
		"quantity" : bundle_qty * panel_qty_dict[panel],
		"supplier" : from_location,
		"posting_date": doc.posting_date,
		"posting_time": doc.posting_time,
		"voucher_type": doc.doctype,
		"voucher_no": doc.name,
		"collapsed_bundle": 1,
		"shade": "NA",
		"quantity_after_transaction": bundle_qty * panel_qty_dict[panel],
		"set_combination": frappe.json.dumps(set_combination),
	}
	d['doctype'] = 'SD YRP Cut Bundle Movement Ledger'
	new_doc = frappe.get_doc(d)
	new_doc.flags.ignore_permissions = 1
	new_doc.set_posting_datetime()
	new_doc.set_key()
	new_doc.submit()

def _filter_set_combination(rows, set_combination):
	if set_combination is None:
		return rows
	target = _collapsed_set_combination_key(set_combination)
	return [
		row
		for row in rows
		if _collapsed_set_combination_key(row.get("set_combination")) == target
	]


def get_collapsed_future_cbm_list(
	posting_date,
	posting_time,
	supplier,
	variant,
	limit=True,
	*,
	lot=None,
	set_combination=None,
):
	query = """
		SELECT name, quantity_after_transaction, set_combination, quantity,
			posting_datetime, creation, voucher_type, voucher_no
		FROM `tabSD YRP Cut Bundle Movement Ledger`
		WHERE collapsed_bundle = 1 AND is_cancelled = 0 AND transformed = 0 AND posting_datetime > %(datetime)s
		AND supplier = %(supplier)s AND item_variant = %(variant)s
		AND (%(lot)s IS NULL OR lot = %(lot)s)
		ORDER BY posting_datetime DESC, creation DESC, name DESC
	"""

	datetime = get_combine_datetime(posting_date,posting_time)
	cbm_list = frappe.db.sql(query, {
		"datetime": datetime,
		"supplier": supplier,
		"variant": variant,
		"lot": lot,
	}, as_dict=True)
	cbm_list = _filter_set_combination(cbm_list, set_combination)
	if limit:
		cbm_list = cbm_list[:1]
	return cbm_list


def get_collapsed_previous_cbm_list(
	posting_date,
	posting_time,
	supplier,
	variant,
	limit=True,
	*,
	lot=None,
	set_combination=None,
):
	query = """
		SELECT name, quantity_after_transaction, quantity, set_combination,
			posting_datetime, creation, voucher_type, voucher_no
		FROM `tabSD YRP Cut Bundle Movement Ledger`
		WHERE collapsed_bundle = 1 AND is_cancelled = 0 AND transformed = 0 AND posting_datetime <= %(datetime)s
		AND supplier = %(supplier)s AND item_variant = %(variant)s
		AND (%(lot)s IS NULL OR lot = %(lot)s)
		ORDER BY posting_datetime DESC, creation DESC, name DESC
	"""

	datetime = get_combine_datetime(posting_date,posting_time)
	cbm_list = frappe.db.sql(query, {
		"datetime": datetime,
		"supplier": supplier,
		"variant": variant,
		"lot": lot,
	}, as_dict=True)
	cbm_list = _filter_set_combination(cbm_list, set_combination)
	if limit:
		cbm_list = cbm_list[:1]
	return cbm_list

def update_is_cancelled_cbml(docname):
	frappe.db.sql(
		"""
			UPDATE `tabSD YRP Cut Bundle Movement Ledger` SET is_cancelled = 1 WHERE name = %(docname)s
		""", {
			"docname": docname
		}
	)

def update_uncollapsed(from_location, set_combination, lot, primary_val, pack_val, stich_val, item):
	row_set_comb = _collapsed_set_combination_key(set_combination)
	cbm_list = frappe.db.sql(
		"""
			SELECT name, set_combination FROM `tabSD YRP Cut Bundle Movement Ledger` WHERE size = %(size)s AND supplier = %(supplier)s
			AND colour = %(colour)s AND item = %(item)s AND lot = %(lot)s AND transformed = 0
			AND is_cancelled = 0 AND is_collapsed = 1
		""", {
			"supplier": from_location,
			"lot": lot,
			"size": primary_val,
			"colour": pack_val,
			"item": item,
		}, as_dict=True
	)
	for bundle in cbm_list:
		cbm_doc = frappe.get_doc('SD YRP Cut Bundle Movement Ledger', bundle['name'])
		panels = {value.strip() for value in cbm_doc.panel.split(",") if value.strip()}
		if (
			stich_val in panels
			and _collapsed_set_combination_key(cbm_doc.set_combination) == row_set_comb
		):
			frappe.db.sql(
				"""
					UPDATE `tabSD YRP Cut Bundle Movement Ledger` SET is_collapsed = 0 WHERE name = %(cbml_name)s
				""", {
					"cbml_name": bundle['name']
				}
			)

def create_inter_cbml_doc(previous_docname, doctype, docname, quantity, multiplier, posting_date, posting_time):
	collapsed_doc = frappe.get_doc('SD YRP Cut Bundle Movement Ledger', previous_docname)
	d = {
		"lot": collapsed_doc.lot,
		"supplier": collapsed_doc.supplier,
		"supplier_name": collapsed_doc. supplier_name,
		"lay_no": collapsed_doc.lay_no,
		"bundle_no": collapsed_doc.bundle_no,
		"panel": collapsed_doc.panel,
		"shade": collapsed_doc.shade,
		"collapsed_bundle": 1,
		"item_variant": collapsed_doc.item_variant,
		"item": collapsed_doc.item,
		"voucher_type": doctype,
		"voucher_no": docname,
		"size": collapsed_doc.size,
		"colour": collapsed_doc.colour,
		"quantity": quantity * multiplier,
		"quantity_after_transaction": collapsed_doc.quantity_after_transaction + (quantity * multiplier),
		"set_combination": collapsed_doc.set_combination,
		"posting_date": posting_date,
		"posting_time": posting_time,
	}
	d['doctype'] = 'SD YRP Cut Bundle Movement Ledger'
	new_doc = frappe.get_doc(d)
	new_doc.flags.ignore_permissions = 1
	new_doc.set_posting_datetime()
	new_doc.set_key()
	new_doc.submit()

def update_future_entries_qty_after_transaction(docname, qty):
	frappe.db.sql(
		"""
			UPDATE `tabSD YRP Cut Bundle Movement Ledger` SET quantity_after_transaction = %(quantity)s
			WHERE name = %(docname)s
		""", {
			"docname": docname,
			"quantity": qty,
		}
	)

def get_latest_cbml_for_variant(from_location,lot, primary_value, pack_value, stich_value, item):
	rows = frappe.db.sql("""
		SELECT name, cbm_key, panel, set_combination, posting_datetime, creation
		FROM `tabSD YRP Cut Bundle Movement Ledger`
		WHERE is_cancelled = 0 AND is_collapsed = 0 AND transformed = 0
		AND collapsed_bundle = 0 AND supplier = %(from_location)s AND lot = %(lot)s
		AND size = %(size)s AND colour = %(colour)s AND item = %(item)s
		ORDER BY posting_datetime DESC, creation DESC, name DESC
	""", {
		"from_location": from_location,
		"lot": lot,
		"size": primary_value,
		"colour": pack_value,
		"item": item,
	}, as_dict=True)
	latest = []
	seen = set()
	for row in rows:
		panels = {value.strip() for value in row.panel.split(",") if value.strip()}
		if stich_value not in panels:
			continue
		key = (row.cbm_key, _collapsed_set_combination_key(row.set_combination))
		if key in seen:
			continue
		seen.add(key)
		latest.append(frappe._dict(name=row.name))
	return latest

def check_dependent_stage_variant(variant, dependent_attribute, dependent_attribute_value):
	attr_details = frappe.db.sql(
		"""
			SELECT attribute, attribute_value FROM `tabYRP Item Variant Attribute` WHERE parent = %(parent)s
			AND attribute = %(dependent)s AND attribute_value = %(stage_value)s
		""", {
			"parent": variant,
			"dependent": dependent_attribute,
			"stage_value": dependent_attribute_value
		}, as_dict=True
	)
	if attr_details:
		return True
	return False

def on_doctype_update():
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["cbm_key"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["item_variant"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["supplier", "posting_datetime"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["supplier", "item_variant"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["item"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["supplier", "lot"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["size", "colour", "item", "panel", "lot"])
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ['is_cancelled', "is_collapsed", "transformed"])
	# prefix serves the list-view SELECT DISTINCT voucher_type; full index serves
	# the (voucher_type, voucher_no) lookups used on submit/cancel flows
	frappe.db.add_index('SD YRP Cut Bundle Movement Ledger', ["voucher_type", "voucher_no"])


CutBundleMovementLedger = SDYRPCutBundleMovementLedger
