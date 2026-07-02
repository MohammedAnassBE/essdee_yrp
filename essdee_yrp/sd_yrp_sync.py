import copy
import json

import frappe
from frappe import STANDARD_USERS
from frappe.model import no_value_fields
from frappe.model.rename_doc import rename_doc


SD_YRP_TOPIC = "sd_yrp_master"

EXACT_MATCH_DOCTYPES = (
	"Item Attribute",
	"Item Attribute Value",
	"UOM",
	"Item Group",
	"Brand",
	"Product Category",
	"Additional Parameter Key",
	"Additional Parameter Value",
	"Department",
	"Terms and Condition",
	"Country",
	"Product Season",
	"Process",
	"Production Term",
	"Item Item Attribute Mapping",
	"Item Dependent Attribute Mapping",
	"Item Variant",
	"Item Category",
	"Item BOM Attribute Mapping",
	"Address",
	"Contact",
)

CUSTOM_MAPPER_DOCTYPES = (
	"Item",
	"Supplier",
	"User",
	"Lot Template",
	"Item Production Detail",
	"Production Order",
	"Lot",
	"MRP Settings",
)

SYNC_DOCTYPES = EXACT_MATCH_DOCTYPES + CUSTOM_MAPPER_DOCTYPES
HANDLER_PATH = "essdee_yrp.sd_yrp_sync.handle_sd_yrp_message"

TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}
# Fieldtypes that carry no DB column (HTML, Section/Column Break, Button, Fold,
# Heading, ...). They must be dropped before a db-level set_value/db_insert or
# MariaDB raises "Unknown column" (e.g. Warehouse.address_html on supplier sync).
# Tables are excluded because filter_doc_fields handles them explicitly.
NO_COLUMN_FIELD_TYPES = set(no_value_fields) - TABLE_FIELD_TYPES
UPSERT_EVENTS = {"after_insert", "first_sync", "on_update", "on_update_after_submit"}

PRODUCTION_ORDER_GRID_ATTRIBUTE = "Size"
PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE = "Stage"
PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE = "Pack"

# creation/modified/modified_by/owner are intentionally KEPT in the payload — the
# consumer re-applies the SOURCE timestamps after each upsert (_apply_source_timestamps)
# so F16 records reflect the source's created/modified, not the sync time.
TRANSIENT_DOC_KEYS = (
	"idx",
	"__onload",
	"_doc_before_save",
	"__last_sync_on",
)

LOT_TIME_AND_ACTION_KEY_PARTS = ("time_and_action",)


def handle_sd_yrp_message(payload):
	header = payload.get("Header") or {}
	doctype = header.get("DocType")
	event = header.get("Event")
	topic = header.get("Topic")

	if topic != SD_YRP_TOPIC:
		frappe.throw(f"Unexpected SD YRP sync topic {topic}")
	if doctype not in SYNC_DOCTYPES:
		frappe.throw(f"{doctype} is not enabled for SD YRP sync")

	if event in UPSERT_EVENTS:
		return upsert_doc(payload.get("Payload") or {}, event=event)
	if event in {"after_rename", "rename"}:
		return rename_synced_doc(payload.get("Payload") or {})
	if event == "on_trash":
		return delete_synced_doc(payload.get("Payload") or {})
	if event == "on_submit":
		return submit_synced_doc(payload.get("Payload") or {})
	if event == "on_cancel":
		return cancel_synced_doc(payload.get("Payload") or {})

	frappe.throw(f"Unsupported SD YRP sync event {event}")


def handle_exact_match(payload):
	return handle_sd_yrp_message(payload)


def upsert_doc(payload, event=None):
	data = clean_payload(payload)
	doctype = data.get("doctype")
	docname = data.get("name")

	if not doctype or not docname:
		frappe.throw("SD YRP sync payload must include doctype and name")

	if doctype == "Item":
		return upsert_item(data)
	if doctype == "Supplier":
		return upsert_supplier(data)
	if doctype == "User":
		return upsert_user(data)
	if doctype == "Country":
		return upsert_country(data)
	if doctype == "Lot Template":
		return upsert_lot_template(data, event=event)
	if doctype == "Item Production Detail":
		return upsert_item_production_detail(data, event=event)
	if doctype == "Production Order":
		return upsert_production_order(data, event=event)
	if doctype == "Lot":
		return upsert_lot(data, event=event)
	if doctype == "Item Dependent Attribute Mapping":
		return upsert_item_dependent_attribute_mapping(data)
	if doctype == "MRP Settings":
		return upsert_mrp_settings(data)

	return upsert_filtered_doc(data)


def upsert_mrp_settings(data):
	# MRP Settings is a Single — write each replicated field straight to tabSingles
	# (DB-level, bypassing validation like the other upserts). Fields the source has
	# but this site's MRP Settings doesn't define are dropped by filter_doc_fields.
	data = filter_doc_fields(data)
	skip = {"doctype", "name", "creation", "owner", "idx", "docstatus", "parent", "parenttype", "parentfield"}
	for fieldname, value in data.items():
		if fieldname in skip:
			continue
		frappe.db.set_single_value("MRP Settings", fieldname, value)
	frappe.clear_document_cache("MRP Settings", "MRP Settings")
	return frappe.get_single("MRP Settings")


_SYNC_SKIP_PARENT_FIELDS = {
	"doctype", "name", "creation", "owner", "idx", "parent", "parenttype", "parentfield", "docstatus",
}


_SOURCE_TIMESTAMP_FIELDS = ("creation", "modified", "owner", "modified_by")


def _apply_source_timestamps(doctype, docname, source):
	# Re-stamp with the SOURCE's creation/modified/owner/modified_by so F16 reflects the
	# source times, not the sync time. update_modified=False keeps `modified` at the
	# source value instead of "now".
	ts = {f: source.get(f) for f in _SOURCE_TIMESTAMP_FIELDS if source.get(f)}
	if ts:
		frappe.db.set_value(doctype, docname, ts, update_modified=False)


def upsert_filtered_doc(data, replace_children=None):
	"""DB-level upsert for replicated data.

	Writes straight to the DB (db_insert / db.set_value), BYPASSING all Frappe
	validation — phone/email format (e.g. the 20-char PHONE_NUMBER_PATTERN), link
	checks, mandatory, and business `validate`. The source (F15) is authoritative;
	any validation discrepancies are cleaned up manually later, not blocked at sync
	time. `replace_children` is accepted for signature compatibility — every child
	table present in the payload is rebuilt. See docs/claude/conventions.md (2026-06-30).
	"""
	source_ts = {f: data.get(f) for f in _SOURCE_TIMESTAMP_FIELDS if data.get(f)}
	data = filter_doc_fields(data)
	doctype = data.get("doctype")
	docname = data.get("name")
	meta = frappe.get_meta(doctype)
	table_fieldnames = {f.fieldname for f in meta.get_table_fields()}

	if frappe.db.exists(doctype, docname):
		parent_values = {
			key: value
			for key, value in data.items()
			if key not in table_fieldnames and key not in _SYNC_SKIP_PARENT_FIELDS
		}
		if parent_values:
			frappe.db.set_value(doctype, docname, parent_values, update_modified=True)
		for field in meta.get_table_fields():
			if field.fieldname not in data:
				continue
			frappe.db.delete(field.options, {"parenttype": doctype, "parent": docname, "parentfield": field.fieldname})
			_db_insert_child_rows(field.options, doctype, docname, field.fieldname, data.get(field.fieldname))
		_apply_source_timestamps(doctype, docname, source_ts)
		return frappe.get_doc(doctype, docname)

	doc = frappe.get_doc(data)
	doc.name = docname
	doc.flags.last_updated_by_sd_yrp_sync = True
	doc.db_insert()
	for field in meta.get_table_fields():
		if field.fieldname not in data:
			continue
		_db_insert_child_rows(field.options, doctype, docname, field.fieldname, data.get(field.fieldname))
	_apply_source_timestamps(doctype, docname, source_ts)
	return doc


def _db_insert_child_rows(child_doctype, parenttype, parent, parentfield, rows):
	idx = 0
	for row in rows or []:
		idx += 1
		row_data = dict(row)
		row_data.update({
			"doctype": child_doctype,
			"parent": parent,
			"parenttype": parenttype,
			"parentfield": parentfield,
			"idx": idx,
		})
		child = frappe.get_doc(row_data)
		if not child.name:
			child.name = frappe.generate_hash(length=10)
		child.flags.last_updated_by_sd_yrp_sync = True
		child.db_insert()


def replace_child_table(doc, fieldname, rows):
	doc.set(fieldname, [])
	for row in rows or []:
		doc.append(fieldname, row)


DEFAULT_ITEM_GROUP = "All Item Groups"


def upsert_item(data):
	# Some legacy source items have a NULL item_group (mandatory on F16). Default
	# them to the root group so the sync doesn't fail; review later by querying
	# Items whose item_group == DEFAULT_ITEM_GROUP and reassign on the source.
	if not data.get("item_group") and frappe.db.exists("Item Group", DEFAULT_ITEM_GROUP):
		data["item_group"] = DEFAULT_ITEM_GROUP
	return upsert_filtered_doc(data)


def upsert_item_dependent_attribute_mapping(data):
	doc = upsert_filtered_doc(data)
	# Back-fill the Item's forward link that was deferred to break the Item<->IDAM
	# cycle. Only when empty, so a genuine source value is never clobbered.
	item = doc.get("item")
	if item and frappe.db.exists("Item", item):
		if not frappe.db.get_value("Item", item, "dependent_attribute_mapping"):
			frappe.db.set_value(
				"Item", item, "dependent_attribute_mapping", doc.name, update_modified=False
			)
	return doc


def upsert_supplier(data):
	supplier_users = data.pop("supplier_users", []) or []
	data.pop("terms_and_condition", None)
	data.pop("price_html", None)

	supplier_doc = upsert_filtered_doc(data)
	sync_supplier_warehouse(supplier_doc.name, data, supplier_users)
	return supplier_doc


def sync_supplier_warehouse(supplier, supplier_data, supplier_users):
	warehouse_name = frappe.db.get_value("Warehouse", {"supplier": supplier}, "name") or supplier
	warehouse_data = {
		"doctype": "Warehouse",
		"name": warehouse_name,
		"name1": warehouse_name,
		"supplier": supplier,
		"disabled": supplier_data.get("disabled"),
		"address_html": supplier_data.get("address_html"),
		"contact_html": supplier_data.get("contact_html"),
		"warehouse_users": get_warehouse_users(supplier_users),
	}
	if frappe.db.exists("Warehouse", warehouse_name):
		warehouse_data["name1"] = frappe.db.get_value("Warehouse", warehouse_name, "name1") or warehouse_name

	return upsert_filtered_doc(warehouse_data, replace_children=("warehouse_users",))


def get_warehouse_users(supplier_users):
	rows = []
	missing_users = []
	seen = set()

	for row in supplier_users:
		user = row.get("user")
		if not user or user in seen:
			continue
		seen.add(user)
		if frappe.db.exists("User", user):
			rows.append({"doctype": "Warehouse User", "user": user})
		else:
			missing_users.append(user)

	if missing_users:
		frappe.log_error(
			title="SD YRP Supplier Warehouse User Sync",
			message=f"Skipped missing users while syncing warehouse: {', '.join(missing_users)}",
		)
	return rows


def upsert_country(data):
	if not data.get("code"):
		if not frappe.db.exists("Country", data.get("name")):
			frappe.log_error(
				title="SD YRP Country Sync",
				message=f"Skipped Country {data.get('name')} because Frappe 16 requires code.",
			)
			return None
		data.pop("code", None)
	return upsert_filtered_doc(data)


def upsert_user(data):
	user = data.get("name") or data.get("email")
	if not user or user in STANDARD_USERS:
		return None

	email = data.get("email") or user
	first_name = data.get("first_name") or email.split("@")[0]
	user_data = {
		"doctype": "User",
		"name": user,
		"email": email,
		"first_name": first_name,
		"last_name": data.get("last_name"),
		"enabled": data.get("enabled"),
		"send_welcome_email": 0,
		"roles": get_user_roles(data.get("roles") or []),
	}
	user_type = data.get("user_type")
	if user_type and frappe.db.exists("User Type", user_type):
		user_data["user_type"] = user_type

	if frappe.db.exists("User", user):
		doc = frappe.get_doc("User", user)
		doc.update(user_data)
		doc.flags.no_welcome_mail = True
		doc.flags.last_updated_by_sd_yrp_sync = True
		doc.save(ignore_permissions=True)
		_apply_source_timestamps("User", user, data)
		return doc

	doc = frappe.get_doc(user_data)
	doc.flags.no_welcome_mail = True
	doc.flags.last_updated_by_sd_yrp_sync = True
	doc.insert(ignore_permissions=True, set_name=user, set_child_names=False)
	_apply_source_timestamps("User", user, data)
	return doc


def get_user_roles(roles):
	rows = []
	missing_roles = []
	seen = set()

	for row in roles:
		role = row.get("role")
		if not role or role in seen:
			continue
		seen.add(role)
		if frappe.db.exists("Role", role):
			rows.append({"doctype": "Has Role", "role": role})
		else:
			missing_roles.append(role)

	if missing_roles:
		frappe.log_error(
			title="SD YRP User Role Sync",
			message=f"Skipped missing roles while syncing user: {', '.join(missing_roles)}",
		)
	return rows


def upsert_lot_template(data, event=None):
	source_context = get_source_context(data, event)
	validate_required_link("Item", data.get("item"), source_context)

	data["bom"] = [
		map_item_bom_row(row, source_context)
		for row in data.get("bom") or []
		if row
	]
	return upsert_filtered_doc(data, replace_children=("bom",))


def map_item_bom_row(row, source_context):
	mapped = copy.deepcopy(row)
	mapped["doctype"] = "Item BOM"
	mapped.pop("name", None)
	mapped.pop("wastage_pct", None)

	row_context = f"{source_context} Item BOM row"
	item = mapped.get("item")
	validate_required_link("Item", item, row_context)

	if mapped.get("attribute_mapping"):
		validate_required_link("Item BOM Attribute Mapping", mapped.get("attribute_mapping"), row_context)

	if not mapped.get("uom"):
		mapped["uom"] = get_item_default_uom(item, row_context)
	validate_required_link("UOM", mapped.get("uom"), row_context)

	return filter_child_row(mapped, "Item BOM")


def upsert_item_production_detail(data, event=None):
	source_context = get_source_context(data, event)
	validate_required_link("Item", data.get("item"), source_context)

	data["item_attributes"] = [
		map_ipd_item_attribute_row(row, source_context)
		for row in data.get("item_attributes") or []
		if row
	]
	data["item_bom"] = [
		map_ipd_bom_row(row, source_context)
		for row in data.get("item_bom") or []
		if row
	]
	data["ipd_processes"] = [
		map_ipd_process_row(row, source_context)
		for row in data.get("ipd_processes") or []
		if row
	]
	return upsert_filtered_doc(
		data,
		replace_children=("item_attributes", "item_bom", "ipd_processes"),
	)


def map_ipd_item_attribute_row(row, source_context=None):
	row_context = f"{source_context} IPD item attribute row" if source_context else "IPD item attribute row"
	attribute = row.get("attribute")
	mapping = row.get("mapping")
	validate_required_link("Item Attribute", attribute, row_context)
	if mapping:
		validate_required_link("Item Item Attribute Mapping", mapping, row_context)

	return filter_child_row(
		{
			"doctype": "IPD Item Attribute",
			"attribute": attribute,
			"mapping": mapping,
		},
		"IPD Item Attribute",
	)


def map_ipd_bom_row(row, source_context):
	return map_item_bom_row(row, f"{source_context} IPD")


def map_ipd_process_row(row, source_context=None):
	row_context = f"{source_context} IPD process row" if source_context else "IPD process row"
	process_name = row.get("process_name")
	stage = row.get("stage")
	validate_required_link("Process", process_name, row_context)
	if stage:
		validate_required_link("Item Attribute Value", stage, row_context)

	return filter_child_row(
		{
			"doctype": "IPD Process",
			"process_name": process_name,
			"in_stage": stage,
			"out_stage": stage,
		},
		"IPD Process",
	)


def upsert_production_order(data, event=None):
	source_context = get_source_context(data, event)
	validate_yrp_settings_for_production_order()
	validate_required_link("Item", data.get("item"), source_context)

	item_rows = map_production_order_item_rows(data)
	data["production_order_details"] = item_rows
	data["production_ordered_details"] = map_production_ordered_rows(data)
	data["item_details"] = get_production_order_item_details_json(data.get("item"), item_rows)

	return upsert_filtered_doc(
		data,
		replace_children=("production_order_details", "production_ordered_details"),
	)


def validate_yrp_settings_for_production_order():
	settings = frappe.get_cached_doc("YRP Settings")
	has_size_grid = any(
		row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE and row.is_grid_attribute
		for row in settings.production_order_attributes or []
	)
	if not has_size_grid:
		frappe.throw(
			"SD YRP Production Order sync requires YRP Settings to have Size as "
			"the grid production order attribute."
		)

	if settings.po_dependent_attribute != PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE:
		frappe.throw(
			"SD YRP Production Order sync requires YRP Settings dependent attribute "
			f"to be {PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE}."
		)
	if settings.po_dependent_attribute_value != PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE:
		frappe.throw(
			"SD YRP Production Order sync requires YRP Settings dependent attribute "
			f"value to be {PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE}."
		)

	validate_required_link("Item Attribute", settings.po_dependent_attribute, "YRP Settings")
	validate_required_link(
		"Item Attribute Value",
		settings.po_dependent_attribute_value,
		"YRP Settings",
	)


def map_production_order_item_rows(data):
	source_context = get_source_context(data)
	item = data.get("item")
	rows = []

	for row in data.get("production_order_details") or []:
		item_variant = row.get("item_variant")
		validate_required_link("Item Variant", item_variant, f"{source_context} Production Order Detail row")
		rows.append({
			"doctype": "Production Order Detail",
			"item": item,
			"item_variant": item_variant,
			"attributes_json": get_variant_attributes_json(item_variant),
			"quantity": row.get("quantity") or 0,
			# Business fields replicated onto essdee_yrp custom fields
			# (fixtures/custom_field.json — synced on every migrate; must be
			# migrated before these columns are written).
			"ratio": row.get("ratio") or 0,
			"mrp": row.get("mrp") or 0,
			"production_order_mrp": row.get("production_order_mrp") or 0,
			"retail_price": row.get("retail_price") or 0,
			"wholesale_price": row.get("wholesale_price") or 0,
		})

	return rows


def map_production_ordered_rows(data):
	source_context = get_source_context(data)
	rows = []

	for row in data.get("production_ordered_details") or []:
		item_variant = row.get("item_variant")
		validate_required_link("Item Variant", item_variant, f"{source_context} Production Ordered Detail row")
		lot = row.get("lot")
		# F15's `lot` Link maps onto base yrp's generic dynamic reference.
		# Lot syncs AFTER Production Order in the initial order, so the lot
		# record may not exist yet — stamp the reference without validating
		# (DB-level sync, source is authoritative).
		rows.append({
			"doctype": "Production Ordered Detail",
			"reference_doctype": "Lot" if lot else None,
			"reference_name": lot,
			"item_variant": item_variant,
			"quantity": row.get("quantity") or 0,
		})

	return rows


def get_variant_attributes_json(item_variant):
	if not item_variant:
		return "{}"

	settings = frappe.get_cached_doc("YRP Settings")
	active_attributes = {
		row.attribute
		for row in settings.production_order_attributes or []
		if row.attribute
	}
	variant = frappe.get_doc("Item Variant", item_variant)
	attributes = {}
	for row in variant.get("attributes") or []:
		if active_attributes and row.attribute not in active_attributes:
			continue
		attributes[row.attribute] = row.attribute_value

	return json.dumps(attributes, separators=(",", ":"))


def get_production_order_item_details_json(item, rows):
	entries = []
	for row in rows or []:
		attributes = json.loads(row.get("attributes_json") or "{}")
		entries.append({
			"attributes": attributes,
			"qty": row.get("quantity") or 0,
		})

	return json.dumps([{"item": item, "entries": entries}], separators=(",", ":"))


def upsert_lot(data, event=None):
	data = strip_lot_time_and_action_fields(data)
	source_context = get_source_context(data, event)

	validate_required_link("Item", data.get("item"), source_context)
	validate_required_link("Production Order", data.get("production_order"), source_context)
	validate_required_link("Item Production Detail", data.get("production_detail"), source_context)
	validate_required_link("Lot Template", data.get("lot_template"), source_context)
	validate_lot_item_variants(data, source_context)

	return upsert_filtered_doc(data)


def validate_lot_item_variants(data, source_context):
	for fieldname, row_key in (
		("items", "item_variant"),
		("lot_order_details", "item_variant"),
		("bom_summary", "item_name"),
		("bom_additional_items", "item_name"),
	):
		for row in data.get(fieldname) or []:
			validate_required_link("Item Variant", row.get(row_key), f"{source_context} {fieldname} row")


def strip_lot_time_and_action_fields(data):
	data = copy.deepcopy(data)
	for key in list(data):
		if is_lot_time_and_action_key(key):
			data.pop(key, None)
	return data


def is_lot_time_and_action_key(key):
	key = (key or "").lower()
	return any(part in key for part in LOT_TIME_AND_ACTION_KEY_PARTS)


def get_item_default_uom(item_code, source_context=None):
	if not item_code:
		frappe.throw(f"Missing Item in {source_context or 'SD YRP sync'}")
	validate_required_link("Item", item_code, source_context or "SD YRP sync")

	uom = frappe.db.get_value("Item", item_code, "default_unit_of_measure")
	if not uom:
		frappe.throw(
			f"Missing default_unit_of_measure for Item {item_code} while syncing "
			f"{source_context or 'SD YRP sync'}"
		)
	validate_required_link("UOM", uom, source_context or f"Item {item_code}")
	return uom


def validate_required_link(doctype, name, source_context):
	if not name:
		return
	if not frappe.db.exists(doctype, name):
		frappe.throw(f"Missing dependency for {source_context}: {doctype} {name}")


def get_source_context(data, event=None):
	context = f"{data.get('doctype') or 'Document'} {data.get('name') or ''}".strip()
	if event:
		context = f"{context} ({event})"
	return context


def rename_synced_doc(payload):
	data = clean_payload(payload)
	doctype = data.get("doctype")
	rename_meta = data.get("rename_meta") or {}
	old_name = rename_meta.get("old_name")
	new_name = rename_meta.get("new_name")

	if not (doctype and old_name and new_name):
		frappe.throw("SD YRP rename payload must include doctype, old_name and new_name")
	if doctype == "User" and old_name in STANDARD_USERS:
		return None

	if not frappe.db.exists(doctype, old_name):
		if frappe.db.exists(doctype, new_name):
			data["name"] = new_name
			return upsert_doc(data, event="after_rename")
		return None

	renamed_doc = rename_doc(
		doctype=doctype,
		old=old_name,
		new=new_name,
		merge=bool(rename_meta.get("merge")),
		ignore_permissions=True,
		ignore_if_exists=True,
		rebuild_search=False,
	)

	if doctype == "Supplier":
		rename_supplier_warehouse(old_name, new_name)

	if doctype in CUSTOM_MAPPER_DOCTYPES:
		data["name"] = new_name
		return upsert_doc(data, event="after_rename")

	return renamed_doc


def rename_supplier_warehouse(old_supplier, new_supplier):
	warehouse = (
		frappe.db.get_value("Warehouse", {"supplier": new_supplier}, "name")
		or frappe.db.get_value("Warehouse", {"supplier": old_supplier}, "name")
	)

	if not warehouse and frappe.db.exists("Warehouse", old_supplier):
		warehouse = old_supplier

	if not warehouse:
		return

	if warehouse == old_supplier and not frappe.db.exists("Warehouse", new_supplier):
		rename_doc(
			doctype="Warehouse",
			old=old_supplier,
			new=new_supplier,
			ignore_permissions=True,
			ignore_if_exists=True,
			rebuild_search=False,
		)
		warehouse = new_supplier

	if frappe.db.exists("Warehouse", warehouse):
		frappe.db.set_value("Warehouse", warehouse, "supplier", new_supplier)


def delete_synced_doc(payload):
	data = clean_payload(payload)
	doctype = data.get("doctype")
	docname = data.get("name")
	if not (doctype and docname):
		frappe.throw("SD YRP delete payload must include doctype and name")

	if doctype == "User":
		if docname not in STANDARD_USERS and frappe.db.exists("User", docname):
			frappe.db.set_value("User", docname, "enabled", 0)
		return

	if doctype == "Supplier":
		if frappe.db.exists("Supplier", docname):
			frappe.db.set_value("Supplier", docname, "disabled", 1)
		warehouse = frappe.db.get_value("Warehouse", {"supplier": docname}, "name")
		if warehouse:
			frappe.db.set_value("Warehouse", warehouse, "disabled", 1)
		return

	if frappe.db.exists(doctype, docname):
		try:
			frappe.delete_doc(
				doctype=doctype,
				name=docname,
				ignore_permissions=True,
				ignore_missing=True,
			)
		except Exception as exc:
			frappe.throw(
				f"Unable to delete synced {doctype} {docname}. Target links may still exist: {exc}"
			)


def submit_synced_doc(payload):
	data = clean_payload(payload)
	doctype = data.get("doctype")
	docname = data.get("name")
	if not (doctype and docname):
		frappe.throw("SD YRP submit payload must include doctype and name")
	if not frappe.get_meta(doctype).is_submittable:
		return
	if frappe.db.exists(doctype, docname):
		doc = frappe.get_doc(doctype, docname)
		if doc.docstatus == 0:
			doc.flags.last_updated_by_sd_yrp_sync = True
			doc.flags.ignore_permissions = True
			doc.submit()


def cancel_synced_doc(payload):
	data = clean_payload(payload)
	doctype = data.get("doctype")
	docname = data.get("name")
	if not (doctype and docname):
		frappe.throw("SD YRP cancel payload must include doctype and name")
	if not frappe.get_meta(doctype).is_submittable:
		return
	if frappe.db.exists(doctype, docname):
		doc = frappe.get_doc(doctype, docname)
		if doc.docstatus == 1:
			doc.flags.last_updated_by_sd_yrp_sync = True
			doc.flags.ignore_permissions = True
			doc.cancel()


def clean_payload(payload):
	data = copy.deepcopy(payload or {})
	return clean_doc_dict(data)


def clean_doc_dict(value):
	if isinstance(value, dict):
		for key in TRANSIENT_DOC_KEYS:
			value.pop(key, None)
		for key, child_value in list(value.items()):
			value[key] = clean_doc_dict(child_value)
	elif isinstance(value, list):
		return [clean_doc_dict(row) for row in value]
	return value


def filter_doc_fields(data):
	doctype = data.get("doctype")
	if not doctype:
		return data

	meta = frappe.get_meta(doctype)
	filtered = {
		"doctype": doctype,
		"name": data.get("name"),
	}
	if "docstatus" in data:
		filtered["docstatus"] = data.get("docstatus")

	for field in meta.fields:
		fieldname = field.fieldname
		if not fieldname or fieldname not in data:
			continue

		if field.fieldtype in TABLE_FIELD_TYPES:
			filtered[fieldname] = [
				filter_child_row(row, field.options)
				for row in data.get(fieldname) or []
				if row
			]
		elif field.fieldtype in NO_COLUMN_FIELD_TYPES:
			# HTML/Section Break/etc. — no DB column, would break set_value
			continue
		else:
			filtered[fieldname] = data.get(fieldname)

	return filtered


def filter_child_row(row, child_doctype):
	if not child_doctype:
		return row

	meta = frappe.get_meta(child_doctype)
	filtered = {"doctype": child_doctype}
	if row.get("name"):
		filtered["name"] = row.get("name")
	if "docstatus" in row:
		filtered["docstatus"] = row.get("docstatus")

	for field in meta.fields:
		fieldname = field.fieldname
		if fieldname and fieldname in row:
			filtered[fieldname] = row.get(fieldname)
	return filtered


def ensure_consumer_config():
	table = "Spine Consumer Handler Mapping"
	parent = "Spine Consumer Config"
	changed = False
	now = frappe.utils.now()

	for doctype in SYNC_DOCTYPES:
		existing_name = frappe.db.get_value(
			table,
			{
				"parent": parent,
				"parenttype": parent,
				"parentfield": "configs",
				"document_type": doctype,
				"topic": SD_YRP_TOPIC,
			},
			"name",
		)

		if existing_name:
			current_handler = frappe.db.get_value(table, existing_name, "event_handler")
			if current_handler != HANDLER_PATH:
				frappe.db.set_value(
					table,
					existing_name,
					"event_handler",
					HANDLER_PATH,
					update_modified=True,
				)
				changed = True
			continue

		next_idx = (
			frappe.db.sql(
				f"""
				select coalesce(max(idx), 0) + 1
				from `tab{table}`
				where parent = %s and parenttype = %s and parentfield = %s
				""",
				(parent, parent, "configs"),
			)[0][0]
			or 1
		)
		row_name = frappe.generate_hash(length=10)

		frappe.db.sql(
			f"""
			insert into `tab{table}`
				(name, creation, modified, modified_by, owner, docstatus, idx,
				 parent, parentfield, parenttype, document_type, topic, event_handler)
			values
				(%s, %s, %s, %s, %s, 0, %s,
				 %s, %s, %s, %s, %s, %s)
			""",
			(
				row_name,
				now,
				now,
				frappe.session.user,
				frappe.session.user,
				next_idx,
				parent,
				"configs",
				parent,
				doctype,
				SD_YRP_TOPIC,
				HANDLER_PATH,
			),
		)
		changed = True

	if changed:
		frappe.clear_document_cache(parent, parent)

	ensure_consumer_processing_enabled()


def ensure_consumer_processing_enabled():
	parent = "Spine Consumer Config"
	changed = False

	for field, value in (
		("bulk_process", "1"),
		# Larger window than the stock 5 so an initial-sync batch drains quickly,
		# but moderate so a single tick's transaction stays bounded for heavy
		# child-table doctypes (Production Order / Lot).
		("msg_window_size", "100"),
	):
		current = frappe.db.sql(
			"""
			select value
			from `tabSingles`
			where doctype = %s and field = %s
			""",
			(parent, field),
		)

		if current:
			if current[0][0] == value:
				continue
			frappe.db.sql(
				"""
				update `tabSingles`
				set value = %s
				where doctype = %s and field = %s
				""",
				(value, parent, field),
			)
		else:
			frappe.db.sql(
				"""
				insert into `tabSingles` (doctype, field, value)
				values (%s, %s, %s)
				""",
				(parent, field, value),
			)
		changed = True

	if changed:
		frappe.clear_document_cache(parent, parent)
