import frappe
from frappe.utils import cint, flt

from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.item_dependent_attribute_mapping.item_dependent_attribute_mapping import (
	get_dependent_attribute_details,
)


def is_cloth_ipd(doc):
	"""Cloth-item IPDs skip every garment validation/mutation in this module."""
	if doc.get("is_cloth_item"):
		return True
	if not doc.get("item"):
		return False
	return bool(frappe.db.get_value("Item", doc.item, "is_cloth_item"))


def before_validate(doc, method=None):
	if is_cloth_ipd(doc):
		return
	apply_ipd_settings_defaults(doc)
	validate_duplicate_bom_items(doc)
	save_combination_detail_fields(doc)
	clear_set_item_fields_when_disabled(doc)
	validate_cloth_detail_names(doc)
	sync_cutting_cloth_select_list(doc)
	sync_marker_groups(doc)
	validate_set_item_defaults(doc)


def validate(doc, method=None):
	validate_common(doc)
	if is_cloth_ipd(doc):
		validate_cloth_ipd(doc)
	else:
		validate_garment_ipd(doc)


def validate_common(doc):
	"""Runs for every IPD kind: the IPD must own its attribute mappings."""
	if doc.is_new():
		create_new_mapping_values(doc)
	ensure_ipd_owned_mappings(doc)
	update_mapping_values(doc)


def validate_garment_ipd(doc):
	validate_packing_fields(doc)
	validate_stiching_fields(doc)
	validate_cutting_fields(doc)
	validate_accessory_fields(doc)
	sync_emblishment_processes(doc)


def validate_cloth_ipd(doc):
	"""Cloth IPDs skip every garment validation (packing/stitching/cutting).
	Fabric tabs: each mapping must be complete, and a (dia, from_colour) /
	(colour, from_dia) pair may appear only once — a blank dia/colour means
	"applies to every value" and counts as its own key."""
	# The engine resolves matrices per process_name with subset attr matching —
	# two fabric tabs sharing one Process master would cross-match groups.
	fabric_processes = [p for p in (doc.knitting_process, doc.dyeing_process, doc.compacting_process) if p]
	if len(fabric_processes) != len(set(fabric_processes)):
		frappe.throw("Knitting, Dyeing and Compacting must each use a DIFFERENT Process master.")

	# The Process master should declare each tab's transformation shape
	# (is_item_conversion / value_change_attributes) — warn when unmaintained.
	from essdee_yrp.fabric_ipd import validate_fabric_process_shapes
	validate_fabric_process_shapes(doc)

	# Extra chain steps (Re-Compacting etc.): distinct masters + complete mappings.
	from essdee_yrp.fabric_chain import validate_fabric_chain
	validate_fabric_chain(doc)

	# Identity-process rows may only treat this IPD's cloth or its yarn.
	allowed_items = {doc.item, doc.get("yarn_item")}
	for row in doc.get("ipd_processes") or []:
		if row.get("process_item") and row.process_item not in allowed_items:
			frappe.throw(
				f"Row {row.idx} of IPD Processes: Process Item {row.process_item} must be "
				f"this IPD's item ({doc.item}) or its yarn ({doc.get('yarn_item') or 'not set'})."
			)

	if doc.knitting_process and flt(doc.get("cloth_per_kg_yarn")) <= 0:
		frappe.throw(
			"Enter 'Cloth Kgs per 1 Kg Yarn' on the Knitting tab — the Work Order "
			"needs the yarn to cloth quantity relationship."
		)
	if doc.dyeing_process:
		validate_swap_rows(
			doc.get("dyeing_colour_details") or [],
			"Dyeing Colour Detail", "dia", "from_colour", "to_colour",
		)
	if doc.compacting_process:
		validate_swap_rows(
			doc.get("compacting_dia_details") or [],
			"Compacting Dia Detail", "colour", "from_dia", "to_dia",
		)


def validate_swap_rows(rows, table_label, pin_field, from_field, to_field):
	seen = set()
	for row in rows:
		if not row.get(from_field) or not row.get(to_field):
			frappe.throw(f"Row {row.idx} of {table_label}: enter both the from and to values.")
		key = (row.get(pin_field) or "", row.get(from_field))
		if key in seen:
			pin = row.get(pin_field) or "all"
			frappe.throw(
				f"Row {row.idx} of {table_label}: duplicate mapping for "
				f"{from_field.replace('_', ' ')} {row.get(from_field)} ({pin_field}: {pin})."
			)
		seen.add(key)


def on_update(doc, method=None):
	for mapping in getattr(frappe.flags, "delete_bom_mapping", []) or []:
		frappe.delete_doc(
			"Item BOM Attribute Mapping",
			mapping,
			force=True,
			ignore_permissions=True,
			ignore_missing=True,
		)
	frappe.flags.delete_bom_mapping = []


def on_trash(doc, method=None):
	# Never delete a mapping still referenced outside this IPD — by an Item or
	# another IPD (legacy cloth IPDs shared docs before ensure_ipd_owned_mappings).
	documents = {
		"Item Item Attribute Mapping": [],
		"Item Dependent Attribute Mapping": [],
		"Item BOM Attribute Mapping": [],
	}
	for attribute in doc.get("item_attributes") or []:
		if attribute.mapping:
			if not is_mapping_shared("Item Item Attribute Mapping", attribute.mapping, doc.name):
				documents["Item Item Attribute Mapping"].append(attribute.mapping)
			attribute.mapping = None

	if doc.dependent_attribute_mapping:
		if not is_mapping_shared("Item Dependent Attribute Mapping", doc.dependent_attribute_mapping, doc.name):
			documents["Item Dependent Attribute Mapping"].append(doc.dependent_attribute_mapping)
		doc.dependent_attribute_mapping = None

	for bom in doc.get("item_bom") or []:
		if bom.attribute_mapping:
			if not is_mapping_shared("Item BOM Attribute Mapping", bom.attribute_mapping, doc.name):
				documents["Item BOM Attribute Mapping"].append(bom.attribute_mapping)
			bom.attribute_mapping = None

	delete_docs(documents)


def validate_duplicate_bom_items(doc):
	items = []
	for row in doc.get("item_bom") or []:
		if not row.based_on_attribute_mapping:
			if row.item in items:
				frappe.throw(f"Duplicate Item in BOM {row.item} in Row {row.idx}")
			items.append(row.item)


def apply_ipd_settings_defaults(doc):
	if not doc.is_new() or not frappe.db.exists("DocType", "IPD Settings"):
		return

	settings = frappe.get_single("IPD Settings")
	defaults = {
		"packing_process": "default_packing_process",
		"pack_in_stage": "default_pack_in_stage",
		"pack_out_stage": "default_pack_out_stage",
		"packing_attribute": "default_packing_attribute",
		"stiching_process": "default_stitching_process",
		"stiching_attribute": "default_stitching_attribute",
		"stiching_in_stage": "default_stitching_in_stage",
		"stiching_out_stage": "default_stitching_out_stage",
		"cutting_process": "default_cutting_process",
	}
	for fieldname, setting_fieldname in defaults.items():
		if doc.meta.get_field(fieldname) and not doc.get(fieldname):
			doc.set(fieldname, settings.get(setting_fieldname))


def save_combination_detail_fields(doc):
	if doc.get("set_item_detail") and doc.is_set_item:
		doc.set("set_item_combination_details", save_item_details(doc.set_item_detail))

	if doc.get("stiching_item_detail"):
		doc.set(
			"stiching_item_combination_details",
			save_item_details(doc.stiching_item_detail, ipd_doc=doc),
		)


def clear_set_item_fields_when_disabled(doc):
	if doc.is_set_item:
		return

	doc.set("set_item_combination_details", [])
	doc.major_attribute_value = None
	doc.set_item_attribute = None


def validate_cloth_detail_names(doc):
	names = [row.name1 for row in doc.get("cloth_detail") or []]
	if len(set(names)) != len(names):
		frappe.throw("Duplicates are occured in the cloth detail")


def sync_cutting_cloth_select_list(doc):
	cut_json = update_if_string_instance(doc.cutting_cloths_json)
	if not isinstance(cut_json, dict) or not cut_json:
		return

	cut_json["select_list"] = [row.name1 for row in doc.get("cloth_detail") or []]
	doc.cutting_cloths_json = cut_json


def sync_marker_groups(doc):
	if not doc.get("marker_details"):
		return

	group_rows = []
	for item in doc.marker_details:
		selected = item.get("selected") or []
		selected.sort()
		group_panels = ",".join(selected)
		if group_panels:
			group_rows.append({"group_panels": group_panels})
	doc.set("cutting_marker_groups", group_rows)


def validate_set_item_defaults(doc):
	if not doc.is_set_item or doc.is_new() or not frappe.db.exists("Item Production Detail", doc.name):
		return

	previous_is_set_item = frappe.db.get_value("Item Production Detail", doc.name, "is_set_item")
	if not previous_is_set_item:
		return

	mapping = get_attribute_mapping(doc, doc.set_item_attribute)
	if not mapping:
		frappe.throw(f"Mapping is required for Set Item Attribute {doc.set_item_attribute}")

	map_doc = frappe.get_cached_doc("Item Item Attribute Mapping", mapping)
	map_values = [row.attribute_value for row in map_doc.values]

	check_dict = {}
	for row in doc.get("stiching_item_details") or []:
		if row.is_default:
			if check_dict.get(row.set_item_attribute_value):
				frappe.throw(f"Select only one Is Default for {row.set_item_attribute_value}")
			check_dict[row.set_item_attribute_value] = 1

	if len(check_dict) < len(map_values):
		frappe.throw("Select Is default for all Set Item Attributes")


def create_new_mapping_values(doc):
	for attribute in doc.get("item_attributes") or []:
		if attribute.mapping:
			source = frappe.get_cached_doc("Item Item Attribute Mapping", attribute.mapping)
			copy = frappe.copy_doc(source)
			copy.insert(ignore_permissions=True)
			attribute.mapping = copy.name

	if doc.dependent_attribute_mapping:
		source = frappe.get_cached_doc("Item Dependent Attribute Mapping", doc.dependent_attribute_mapping)
		copy = frappe.copy_doc(source)
		copy.insert(ignore_permissions=True)
		doc.dependent_attribute_mapping = copy.name

	for bom in doc.get("item_bom") or []:
		if bom.based_on_attribute_mapping and bom.attribute_mapping:
			source = frappe.get_doc("Item BOM Attribute Mapping", bom.attribute_mapping)
			copy = frappe.copy_doc(source)
			set_if_has_field(copy, "item", doc.item)
			set_if_has_field(copy, "bom_item", bom.item)
			set_if_has_field(copy, "item_production_detail", doc.name)
			copy.insert(ignore_permissions=True)
			bom.attribute_mapping = copy.name
		else:
			bom.attribute_mapping = None


def ensure_ipd_owned_mappings(doc):
	"""An IPD must never share mapping documents with an Item or another IPD —
	it keeps its own copies so they can diverge. Replaces any shared mapping
	(legacy cloth IPDs, duplicated IPDs, re-selecting the item on a saved IPD)
	with a fresh copy."""
	for attribute in doc.get("item_attributes") or []:
		if attribute.mapping and is_mapping_shared("Item Item Attribute Mapping", attribute.mapping, doc.name):
			source = frappe.get_cached_doc("Item Item Attribute Mapping", attribute.mapping)
			copy = frappe.copy_doc(source)
			copy.insert(ignore_permissions=True)
			attribute.mapping = copy.name

	if doc.dependent_attribute_mapping and is_mapping_shared(
		"Item Dependent Attribute Mapping", doc.dependent_attribute_mapping, doc.name
	):
		source = frappe.get_cached_doc("Item Dependent Attribute Mapping", doc.dependent_attribute_mapping)
		copy = frappe.copy_doc(source)
		copy.insert(ignore_permissions=True)
		doc.dependent_attribute_mapping = copy.name

	for bom in doc.get("item_bom") or []:
		if bom.attribute_mapping and is_mapping_shared("Item BOM Attribute Mapping", bom.attribute_mapping, doc.name):
			source = frappe.get_doc("Item BOM Attribute Mapping", bom.attribute_mapping)
			copy = frappe.copy_doc(source)
			set_if_has_field(copy, "item", doc.item)
			set_if_has_field(copy, "bom_item", bom.item)
			copy.insert(ignore_permissions=True)
			bom.attribute_mapping = copy.name


def is_mapping_shared(doctype, name, ipd_name):
	"""True when a mapping doc is referenced outside this IPD — by an Item's
	attribute rows / dependent mapping, or by another IPD. Shared docs must
	never be deleted and get replaced by an owned copy on save. The current
	item alone is not enough to check: a legacy duplicate can carry mappings
	belonging to a DIFFERENT item than doc.item."""
	if doctype == "Item Item Attribute Mapping":
		return bool(
			frappe.db.exists("Item Item Attribute", {"mapping": name})
			or frappe.db.exists("IPD Item Attribute", {"mapping": name, "parent": ["!=", ipd_name]})
		)
	if doctype == "Item Dependent Attribute Mapping":
		return bool(
			frappe.db.exists("Item", {"dependent_attribute_mapping": name})
			or frappe.db.exists(
				"Item Production Detail", {"dependent_attribute_mapping": name, "name": ["!=", ipd_name]}
			)
		)
	if doctype == "Item BOM Attribute Mapping":
		return bool(frappe.db.exists("Item BOM", {"attribute_mapping": name, "parent": ["!=", ipd_name]}))
	return False


def update_mapping_values(doc):
	for attribute in doc.get("item_attributes") or []:
		if not attribute.mapping:
			mapping = frappe.new_doc("Item Item Attribute Mapping")
			mapping.attribute_name = attribute.attribute
			mapping.insert(ignore_permissions=True)
			attribute.mapping = mapping.name

	frappe.flags.delete_bom_mapping = []
	for bom in doc.get("item_bom") or []:
		if bom.based_on_attribute_mapping and not bom.attribute_mapping:
			mapping = frappe.new_doc("Item BOM Attribute Mapping")
			set_if_has_field(mapping, "item_production_detail", doc.name)
			set_if_has_field(mapping, "item", doc.item)
			set_if_has_field(mapping, "bom_item", bom.item)

			item_attribute_rows = []
			if doc.packing_attribute:
				item_attribute_rows.append({"attribute": doc.packing_attribute})
			mapping.set("item_attributes", item_attribute_rows)
			mapping.set("bom_item_attributes", get_item_attribute_rows(bom.item))
			mapping.flags.ignore_validate = True
			mapping.insert(ignore_permissions=True)
			bom.attribute_mapping = mapping.name

		elif not bom.based_on_attribute_mapping and bom.attribute_mapping:
			frappe.flags.delete_bom_mapping.append(bom.attribute_mapping)
			bom.attribute_mapping = None


def validate_packing_fields(doc):
	if doc.is_new():
		return

	if doc.based_on_other_attribute_mapping:
		if doc.packing_mode == "Size Ratio Packing":
			validate_packing_size_details(doc, ratio_mode=True)
		elif doc.packing_mode == "Size Wise Packing":
			validate_packing_size_details(doc, ratio_mode=False)
			doc.packing_combo = 1
		else:
			validate_packing_assortment(doc)
		return

	validate_packing_attribute_details(doc)


def validate_packing_attribute_details(doc):
	if cint(doc.packing_combo) == 0:
		frappe.throw("The packing combo should not be zero")

	if cint(doc.packing_attribute_no) == 0:
		frappe.throw("The packing attribute no should not be zero")

	if not doc.packing_attribute:
		frappe.throw("Packing Attribute is required")

	mapping = get_attribute_mapping(doc, doc.packing_attribute)
	if not mapping:
		frappe.throw(f"Mapping is required for Packing Attribute {doc.packing_attribute}")

	map_doc = frappe.get_cached_doc("Item Item Attribute Mapping", mapping)
	if len(map_doc.values) < cint(doc.packing_attribute_no):
		frappe.throw(
			f"The Packing attribute no is {doc.packing_attribute_no} "
			f"But there is only {len(map_doc.values)} attributes are available"
		)

	rows = doc.get("packing_attribute_details") or []
	if len(rows) != cint(doc.packing_attribute_no):
		frappe.throw(f"Only {doc.packing_attribute_no} {doc.packing_attribute}'s are required")

	attributes = set()
	if doc.auto_calculate:
		for row in rows:
			attributes.add(row.attribute_value)
			row.quantity = 0
	else:
		total = 0.0
		for row in rows:
			if not row.quantity:
				frappe.throw(
					"Enter value in Packing Attribute Details, Zero is not considered as a valid quantity"
				)
			total += flt(row.quantity)
			attributes.add(row.attribute_value)

		if total != flt(doc.packing_combo):
			frappe.throw(
				f"In Packing Attribute Details, the sum of quantity should be {doc.packing_combo}"
			)

	if len(attributes) != len(rows):
		frappe.throw("Duplicate Attribute values are occured in Packing Attribute Details")


def validate_packing_size_details(doc, ratio_mode):
	rows = doc.get("packing_size_details") or []
	if not rows:
		frappe.throw("Enter the Packing Size Details for the selected Packing Mode.")

	valid_sizes = get_ipd_attribute_values(doc, doc.primary_item_attribute)
	seen = set()
	for row in rows:
		if not row.quantity or row.quantity <= 0:
			frappe.throw("Quantity should be greater than zero in Packing Size Details.")
		if row.attribute_value in seen:
			frappe.throw(f"Duplicate size '{row.attribute_value}' in Packing Size Details.")
		seen.add(row.attribute_value)
		if valid_sizes and row.attribute_value not in valid_sizes:
			frappe.throw(
				f"'{row.attribute_value}' is not a valid {doc.primary_item_attribute} for this item."
			)

	if ratio_mode:
		if flt(doc.packing_combo) <= 0:
			frappe.throw(
				"The Packing Combo (pieces per box) should be greater than zero for Size Ratio Packing."
			)
		total = sum(flt(row.quantity) for row in rows)
		if total != flt(doc.packing_combo):
			frappe.throw(
				f"In Packing Size Details, the sum of quantity should be {doc.packing_combo} "
				"(the Packing Combo)."
			)


def validate_packing_assortment(doc):
	data = update_if_string_instance(doc.packing_assortment_json) or {}
	if not data.get("boxes"):
		frappe.throw("Generate the Packing Assortment (Get Packing Combination) before saving.")

	separator_attribute = resolve_packing_separator(doc)
	item_attr_names = {row.attribute for row in doc.get("item_attributes") or []}
	errors = check_assortment_data(data, separator_attribute, item_attr_names)
	if errors:
		frappe.throw("<br>".join(errors))


def validate_stiching_fields(doc):
	if not doc.stiching_process:
		return

	rows = doc.get("stiching_item_details") or []
	if len(rows) == 0:
		frappe.throw("Enter stiching attribute details")

	attributes = set()
	for row in rows:
		if not row.quantity:
			frappe.throw(
				"Enter value in Stiching Item Details, Zero is not considered as a valid quantity"
			)
		attributes.add(row.stiching_attribute_value)

	if len(attributes) != len(rows):
		frappe.throw("Duplicate Attribute values are occured in Stiching Item Details")


def validate_cutting_fields(doc):
	if not doc.cutting_process:
		return

	cloth_attributes = [row.attribute for row in doc.get("cloth_attributes") or []]
	cutting_attributes = [row.attribute for row in doc.get("cutting_attributes") or []]
	accessory_attributes = [row.attribute for row in doc.get("accessory_attributes") or []]

	if (
		not doc.is_same_packing_attribute
		and doc.stiching_attribute
		and doc.stiching_attribute not in cutting_attributes
		and len(cutting_attributes) > 0
	):
		frappe.throw(f"{doc.stiching_attribute} Should be in Cutting Combination")

	if doc.stiching_attribute in cloth_attributes and doc.stiching_attribute not in cutting_attributes:
		frappe.throw(f"Please mention the {doc.stiching_attribute} in Cutting Combination")

	previous_is_set_item = None
	if not doc.is_new() and frappe.db.exists("Item Production Detail", doc.name):
		previous_is_set_item = frappe.db.get_value("Item Production Detail", doc.name, "is_set_item")

	if previous_is_set_item:
		if doc.is_set_item and doc.set_item_attribute not in accessory_attributes and len(accessory_attributes) > 0:
			frappe.throw(f"{doc.set_item_attribute} should be in the Accessory Combination")

		if doc.is_set_item and doc.set_item_attribute not in cutting_attributes and len(cutting_attributes) > 0:
			frappe.throw(f"{doc.set_item_attribute} Should be in the Cutting Combination")

	if doc.is_same_packing_attribute:
		for row in doc.get("stiching_item_combination_details") or []:
			row.attribute_value = row.major_attribute_value


def validate_accessory_fields(doc):
	if len(doc.get("accessory_attributes") or []) == 0:
		return
	if not update_if_string_instance(doc.cloth_accessory_json):
		return
	if not update_if_string_instance(doc.stiching_accessory_json):
		frappe.throw("Enter the Details for Stitching Accessory Combination")


def sync_emblishment_processes(doc):
	emblishment_data = update_if_string_instance(doc.emblishment_details_json)
	if not isinstance(emblishment_data, dict) or not emblishment_data:
		return

	existing = {row.process_name: row for row in doc.get("ipd_processes") or []}
	for process_name in emblishment_data:
		if process_name in existing:
			row = existing[process_name]
			set_process_stage(row, doc.stiching_in_stage)
		else:
			row = {"process_name": process_name}
			set_process_stage(row, doc.stiching_in_stage)
			doc.append("ipd_processes", row)


def set_process_stage(row, stage):
	if not stage:
		return
	if isinstance(row, dict):
		row["in_stage"] = stage
		row["out_stage"] = stage
		return
	if row.meta.get_field("stage"):
		row.stage = stage
	else:
		row.in_stage = stage
		row.out_stage = stage


def get_attribute_mapping(doc, attribute):
	for row in doc.get("item_attributes") or []:
		if row.attribute == attribute:
			return row.mapping
	return None


def get_item_attribute_rows(item):
	if not item or not frappe.db.exists("Item", item):
		return []

	item_doc = frappe.get_cached_doc("Item", item)
	return [{"attribute": row.attribute} for row in item_doc.get("attributes") or []]


def get_ipd_attribute_values(doc, attribute):
	if not attribute:
		return []
	mapping = get_attribute_mapping(doc, attribute)
	if not mapping:
		return []

	map_doc = frappe.get_cached_doc("Item Item Attribute Mapping", mapping)
	return [row.attribute_value for row in map_doc.values]


def resolve_packing_separator(doc):
	dependent = get_dependent_attribute_details(doc.dependent_attribute_mapping)
	pack_stage_attrs = dependent["attr_list"].get(doc.pack_out_stage, {}).get("attributes") or []
	if len(pack_stage_attrs) != 1:
		frappe.throw(
			"Packing assortment needs the pack-out stage to keep exactly ONE box attribute "
			f"(the separator), but it keeps {pack_stage_attrs}. Set the Item Dependent Attribute "
			"Mapping pack stage to keep just the box attribute."
		)
	return pack_stage_attrs[0]


def check_assortment_data(data, separator_attribute, item_attr_names):
	errors = []
	boxes = data.get("boxes") or []
	if not boxes:
		errors.append("Generate and fill the Packing Assortment before saving.")
		return errors

	for attr in data.get("assortment_attributes") or []:
		if attr not in item_attr_names:
			errors.append(f"Assortment attribute '{attr}' is not an attribute of this item.")

	for box in boxes:
		rows = box.get("rows") or []
		if sum((row.get("qty") or 0) for row in rows) <= 0:
			errors.append(f"Box '{box.get('box')}' has a zero total quantity.")
		separator_values = {row.get(separator_attribute) for row in rows if separator_attribute in row}
		if box.get("separator_value") is not None:
			separator_values.add(box.get("separator_value"))
		separator_values.discard(None)
		if len(separator_values) > 1:
			errors.append(
				f"Box '{box.get('box')}' mixes more than one {separator_attribute} "
				f"({sorted(separator_values)}). A box may vary only the assorted dimension."
			)
	return errors


def save_item_details(combination_item_detail, ipd_doc=None):
	combination_item_detail = update_if_string_instance(combination_item_detail)
	item_detail = []
	set_item_stitching_attrs = {}
	set_item_packing_combination = {}

	if ipd_doc and ipd_doc.is_set_item:
		set_item_stitching_attrs = get_stich_details(ipd_doc)
		for row in ipd_doc.get("set_item_combination_details") or []:
			set_item_packing_combination.setdefault(row.major_attribute_value, {})
			set_item_packing_combination[row.major_attribute_value][row.set_item_attribute_value] = (
				row.attribute_value
			)

	for idx, item in enumerate(combination_item_detail.get("values") or []):
		for value in item.get("val") or {}:
			row = {
				"index": idx,
				"major_attribute_value": item.get("major_attribute"),
				"set_item_attribute_value": value,
				"attribute_value": item["val"][value],
			}
			if ipd_doc and ipd_doc.is_set_item and set_item_stitching_attrs.get(value):
				part = set_item_stitching_attrs[value]
				row["major_attribute_value"] = set_item_packing_combination[item["major_attribute"]][part]
			item_detail.append(row)
	return item_detail


def get_stich_details(doc):
	return {
		row.stiching_attribute_value: row.set_item_attribute_value
		for row in doc.get("stiching_item_details") or []
	}


def set_if_has_field(doc, fieldname, value):
	if doc.meta.get_field(fieldname):
		doc.set(fieldname, value)


def delete_docs(documents):
	for doctype, names in documents.items():
		if names:
			frappe.db.delete(doctype, {"name": ["in", names]})
