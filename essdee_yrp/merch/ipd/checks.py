"""Run the IPD save rules on a draft and list every problem, without saving anything."""

import copy
import re
from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, flt, strip_html
from yrp.attribute_links import value as attribute_value

from essdee_yrp import ipd_validations as rules
from essdee_yrp.merch.ipd import client_rules
from essdee_yrp.merch.ipd import fields as registry
from essdee_yrp.merch.ipd.draft import apply_patch
from essdee_yrp.merch.ipd.payload import document_attribute_ids, mapping_memo, prime_attribute_values

SAVEPOINT = "merch_ipd_check"
ATTRIBUTE_CACHES = ("attribute_link_values", "attribute_link_names", "attribute_link_context")

RULES = {
	"links": ("item", "item", _("Linked values exist")),
	"normalize_major_value": ("stitching", "stiching_major_attribute_value", _("Stitching major value")),
	"apply_ipd_settings_defaults": ("item", None, _("IPD settings defaults")),
	"sync_cloth_recipe_snapshot": ("yarn_ratio", "yarn_ratio_details", _("Yarn recipe")),
	"reconcile_fabric_route_processes": ("fabric_processes", "fabric_processes", _("Fabric route processes")),
	"sync_panel_wise_consumption_matrix": (
		"cutting",
		"panel_wise_consumption_matrix_json",
		_("Panel-wise consumption"),
	),
	"sync_panel_wise_cloth_mapping_matrix": (
		"cutting",
		"panel_wise_cloth_mapping_json",
		_("Panel-wise cloth"),
	),
	"validate_duplicate_bom_items": ("accessories", "item_bom", _("No duplicate BOM items")),
	"save_combination_detail_fields": ("stitching", "stiching_item_detail", _("Combinations")),
	"clear_set_item_fields_when_disabled": ("set_item", "is_set_item", _("Set item fields")),
	"validate_cloth_detail_names": ("cutting", "cloth_detail", _("Unique cloth names")),
	"sync_cutting_cloth_select_list": ("cutting", "cutting_cloths_json", _("Cloth list")),
	"validate_set_item_defaults": ("stitching", "stiching_item_details", _("Default panel per part")),
	"missing_cloth_item_attribute_rows": ("attributes", "item_attributes", _("Fabric attributes")),
	"controller_validate": ("attributes", "item_attributes", _("Item attributes")),
	"validate_colour_yarn_recipes": ("yarn_ratio", "colour_yarn_recipes", _("Colour yarn recipes")),
	"validate_packing_fields": ("packing", "packing_attribute_details", _("Packing")),
	"validate_stiching_fields": ("stitching", "stiching_item_details", _("Stitching panels")),
	"validate_cutting_fields": ("cutting", "cutting_attributes", _("Cutting combination")),
	"validate_accessory_fields": ("accessories", "stiching_accessory_json", _("Accessory combination")),
	"sync_emblishment_processes": ("processes", "emblishment_details_json", _("Embellishment processes")),
	"validate_cloth_ipd": ("fabric_routes", "fabric_routes", _("Cloth production detail")),
	"mandatory": ("item", None, _("Required fields")),
	"data_fields": ("item", None, _("Field formats")),
	"selects": ("item", None, _("Select values")),
	"non_negative": ("item", None, _("No negative values")),
	"length": ("item", None, _("Field lengths")),
}


def garment_steps(doc):
	from essdee_yrp.panel_wise_cloth_mapping import sync_panel_wise_cloth_mapping_matrix
	from essdee_yrp.panel_wise_consumption import sync_panel_wise_consumption_matrix

	return [
		("sync_panel_wise_consumption_matrix", lambda: sync_panel_wise_consumption_matrix(doc)),
		("sync_panel_wise_cloth_mapping_matrix", lambda: sync_panel_wise_cloth_mapping_matrix(doc)),
		("validate_duplicate_bom_items", lambda: rules.validate_duplicate_bom_items(doc)),
		("save_combination_detail_fields", lambda: rules.save_combination_detail_fields(doc)),
		("clear_set_item_fields_when_disabled", lambda: rules.clear_set_item_fields_when_disabled(doc)),
		("validate_cloth_detail_names", lambda: rules.validate_cloth_detail_names(doc)),
		("sync_cutting_cloth_select_list", lambda: rules.sync_cutting_cloth_select_list(doc)),
		("validate_set_item_defaults", lambda: rules.validate_set_item_defaults(doc)),
	]


def cloth_steps(doc):
	from essdee_yrp.fabric_ipd import reconcile_fabric_route_processes

	return [
		("sync_cloth_recipe_snapshot", lambda: rules.sync_cloth_recipe_snapshot(doc)),
		("reconcile_fabric_route_processes", lambda: reconcile_fabric_route_processes(doc)),
	]


def before_validate_steps(doc):
	from essdee_yrp.fabric_ipd import missing_cloth_item_attribute_rows
	from essdee_yrp.ipd_attribute_links import normalize_major_value

	cloth = rules.is_cloth_ipd(doc)
	steps = [
		("normalize_major_value", lambda: normalize_major_value(doc)),
		("apply_ipd_settings_defaults", lambda: rules.apply_ipd_settings_defaults(doc)),
	]
	steps += (
		cloth_steps(doc) if cloth else [("clear_recipes", lambda: clear_recipes(doc)), *garment_steps(doc)]
	)
	if cloth:
		steps.append(("missing_cloth_item_attribute_rows", lambda: missing_cloth_item_attribute_rows(doc)))
	return steps


def clear_recipes(doc):
	if doc.meta.get_field("colour_yarn_recipes"):
		doc.set("colour_yarn_recipes", [])


def validate_steps(doc):
	steps = [
		("controller_validate", doc.validate),
		("validate_colour_yarn_recipes", lambda: rules.validate_colour_yarn_recipes(doc)),
	]
	if rules.is_cloth_ipd(doc):
		return [*steps, ("validate_cloth_ipd", lambda: rules.validate_cloth_ipd(doc))]
	return [
		*steps,
		("validate_packing_fields", lambda: rules.validate_packing_fields(doc)),
		("validate_stiching_fields", lambda: rules.validate_stiching_fields(doc)),
		("validate_cutting_fields", lambda: rules.validate_cutting_fields(doc)),
		("validate_accessory_fields", lambda: rules.validate_accessory_fields(doc)),
		("sync_emblishment_processes", lambda: rules.sync_emblishment_processes(doc)),
	]


def frappe_validator_steps(doc):
	documents = [doc, *doc.get_all_children()]
	return [
		(rule, lambda method=method: [getattr(document, method)() for document in documents])
		for rule, method in (
			("data_fields", "_validate_data_fields"),
			("selects", "_validate_selects"),
			("non_negative", "_validate_non_negative"),
			("length", "_validate_length"),
		)
	]


class CheckRun:
	"""Collects one problem per failing step, in the order a real save runs them."""

	def __init__(self, doc):
		self.doc = doc
		self.problems = []
		self.passed = []

	def run(self, rule, step):
		message_start = len(frappe.get_message_log())
		try:
			step()
		except frappe.ValidationError as error:
			self.add(rule, message_of(error, message_start))
		else:
			if rule in RULES:
				self.passed.append({"rule": rule, "section": RULES[rule][0], "label": RULES[rule][2]})

	def add(self, rule, message, field=None, row_key=None, column=None, section=None, row_label=None):
		section_key, rule_field, _label = RULES.get(rule, (section or "review", field, rule))
		if rule in CLOTH_RULES and row_key is None and field is None:
			cloth = cloth_location(self.doc, message)
			section, field, row_key, column = (
				cloth.get("section"),
				cloth.get("field"),
				cloth.get("row_key"),
				cloth.get("column"),
			)
		field = field or rule_field
		location = locate(self.doc, rule, message) if row_key is None and column is None else {}
		row_key = row_key if row_key is not None else location.get("row_key")
		column = column or location.get("column")
		self.problems.append(
			{
				"key": f"{rule}:{field}:{row_key}:{column}:{len(self.problems)}",
				"section": section or section_key,
				"rule": rule,
				"field": field,
				"row_key": row_key,
				"column": column,
				"row_label": row_label,
				"message": message,
			}
		)

	def result(self, state):
		problems = [entry for entry in self.problems if entry["rule"] not in client_rules.WARNING_RULES]
		warnings = [entry for entry in self.problems if entry["rule"] in client_rules.WARNING_RULES]
		counts = {}
		for problem in problems:
			counts[problem["section"]] = counts.get(problem["section"], 0) + 1
		return {
			"state": state,
			"problems": problems,
			"warnings": warnings,
			"passed": self.passed,
			"section_counts": counts,
		}


def message_of(error, message_start):
	text = strip_html(str(error) or "").strip()
	if not text:
		logged = frappe.get_message_log()[message_start:]
		text = strip_html((logged[-1] or {}).get("message", "")) if logged else ""
	return text or _("This section has a problem.")


def run_mandatory(run, doc):
	missing = [(doc, fieldname, message) for fieldname, message in doc._get_missing_mandatory_fields()]
	for row in doc.get_all_children():
		missing.extend(
			(row, fieldname, message) for fieldname, message in row._get_missing_mandatory_fields()
		)
	for owner, fieldname, _message in missing:
		run.add("mandatory", mandatory_message(owner, fieldname), **mandatory_location(owner, fieldname))
	if not missing:
		run.passed.append({"rule": "mandatory", "section": "item", "label": RULES["mandatory"][2]})


def mandatory_message(owner, fieldname):
	label = _(owner.meta.get_label(fieldname))
	if not owner.get("parentfield"):
		return _("{0} is required.").format(label)
	table = (
		_(owner.parent_doc.meta.get_label(owner.parentfield))
		if owner.get("parent_doc")
		else owner.parentfield
	)
	return _("Row {0} of {1}: {2} is required.").format(owner.idx, table, label)


def run_server_rules(run, doc):
	doc._action = "save"
	doc._set_defaults()
	doc.set_parent_in_children()
	doc.set_name_in_children()
	run.run("links", doc._validate_links)
	for rule, step in before_validate_steps(doc):
		run.run(rule, step)
	for rule, step in validate_steps(doc):
		run.run(rule, step)
	run_mandatory(run, doc)
	for rule, step in frappe_validator_steps(doc):
		run.run(rule, step)


def attach_before_save(doc):
	"""The stored snapshot a real save loads, without taking its row lock."""
	before = frappe.get_doc(registry.DOCTYPE, doc.name)
	doc._doc_before_save = before
	for table in doc._non_computed_table_fieldnames:
		stored = {row.name: row for row in before.get(table) or []}
		for row in doc.get(table) or []:
			row._doc_before_save = stored.get(row.name)


@contextmanager
def isolated_request_state():
	"""Savepoint plus every request-local cache a draft save could touch, restored after."""
	message_start = len(frappe.get_message_log())
	delete_bom_mapping = copy.copy(frappe.flags.get("delete_bom_mapping"))
	frappe.db.savepoint(SAVEPOINT)
	try:
		yield
	finally:
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.flags.delete_bom_mapping = delete_bom_mapping
		del frappe.local.message_log[message_start:]
		for cache in ATTRIBUTE_CACHES:
			if hasattr(frappe.local, cache):
				delattr(frappe.local, cache)
		frappe.db.value_cache.clear()


def run_checks(name=None, values=None):
	"""CheckResult for a stored IPD plus an optional draft patch."""
	if not name:
		return check_new(values or {})
	doc = frappe.get_doc(registry.DOCTYPE, name)
	doc.check_permission("read")
	if doc.approval_status == "Approved":
		return CheckRun(doc).result("approved")
	with isolated_request_state():
		run = check_stored(doc, values or {})
	return run.result("draft")


def check_stored(doc, values):
	attach_before_save(doc)
	prime_attribute_values(document_attribute_ids(doc))
	run = CheckRun(doc)
	try:
		apply_patch(doc, values)
	except frappe.ValidationError as error:
		run.add("patch", message_of(error, len(frappe.get_message_log())), section="review")
		return run
	with mapping_memo(doc):
		desk_problems = client_rules.problems(doc)
		run_server_rules(run, doc)
	for problem in desk_problems:
		run.add(**problem)
	return run


def check_new(values):
	frappe.has_permission(registry.DOCTYPE, "create", throw=True)
	run = CheckRun(frappe.new_doc(registry.DOCTYPE))
	item = (values or {}).get("item")
	if not item:
		run.add("item_required", _("Select an Item."), field="item", section="item")
	elif not frappe.db.exists("Item", item):
		run.add("item_required", _("Item {0} does not exist.").format(item), field="item", section="item")
	else:
		run.passed.append({"rule": "item_required", "section": "item", "label": _("Item chosen")})
	return run.result("new")


def first_row(doc, table, predicate):
	for row in doc.get(table) or []:
		if predicate(row):
			return row
	return None


def mandatory_location(owner, fieldname):
	if not owner.get("parentfield"):
		return {"field": fieldname, "section": registry.section_of(fieldname)}
	table = owner.parentfield
	return {
		"field": table,
		"row_key": browser_row_key(owner),
		"row_label": _("Row {0}").format(owner.idx),
		"column": fieldname,
		"section": registry.section_of(table) or SECTION_OF_READ_ONLY_TABLE.get(table),
	}


CLOTH_RULES = {"validate_cloth_ipd", "validate_colour_yarn_recipes"}
CLOTH_TABLE_LABELS = {
	"Fabric Routes": "fabric_routes",
	"Compacting Reference Details": "compacting_reference_details",
	"Compacting Details": "compacting_reference_details",
	"Colour-wise Yarn Recipes": "colour_yarn_recipes",
	"IPD Processes": "ipd_processes",
}
SECTION_OF_READ_ONLY_TABLE = {"colour_yarn_recipes": "yarn_ratio"}
ROW_OF_TABLE = re.compile(r"^Row (\d+) of ([A-Za-z -]+?)(?=:| duplicates)")
YARN_ROW = re.compile(r"^Row (\d+):")


def cloth_location(doc, message):
	"""Section, table, row and column named by a cloth rule's message."""
	match = ROW_OF_TABLE.match(message)
	if match and match.group(2) in CLOTH_TABLE_LABELS:
		return table_location(doc, CLOTH_TABLE_LABELS[match.group(2)], int(match.group(1)), message)
	if "Yarn" in message:
		row = YARN_ROW.match(message)
		return table_location(doc, "yarn_ratio_details", int(row.group(1)) if row else 0, message)
	if message.startswith("Fabric Routes"):
		return {"section": "fabric_routes", "field": "fabric_routes"}
	return {}


def table_location(doc, table, idx, message):
	rows = doc.get(table) or []
	row = rows[idx - 1] if 0 < idx <= len(rows) else None
	section = registry.section_of(table) or SECTION_OF_READ_ONLY_TABLE.get(table)
	return {
		"section": section,
		"field": table,
		"row_key": browser_row_key(row) if row else None,
		"column": column_named(row, message),
	}


def browser_row_key(row):
	"""Stored rows are keyed by name; rows the draft added by position, as the editor keys them."""
	parent = getattr(row, "parent_doc", None)
	before = parent.get_doc_before_save() if parent else None
	stored = {child.name for child in (before.get(row.parentfield) or [])} if before else set()
	return row.name if row.name in stored else f"new:{row.idx - 1}"


def column_named(row, message):
	if row is None:
		return None
	for field in row.meta.fields:
		if field.label and f"select {field.label}" in message:
			return field.fieldname
	return None


def locate(doc, rule, message):
	"""Best-effort (row_key, column) for the common rule failures."""
	if rule == "validate_stiching_fields":
		row = first_row(doc, "stiching_item_details", lambda row: not cint(row.quantity))
		return {"row_key": attribute_value(row.stiching_attribute_value), "column": "quantity"} if row else {}
	if rule == "validate_packing_fields" and "quantity" in message.lower():
		row = first_row(doc, "packing_attribute_details", lambda row: not flt(row.quantity))
		return {"row_key": attribute_value(row.attribute_value), "column": "quantity"} if row else {}
	if rule == "validate_duplicate_bom_items":
		seen = set()
		for row in doc.get("item_bom") or []:
			if not row.based_on_attribute_mapping:
				if row.item in seen:
					return {"row_key": browser_row_key(row), "column": "item"}
				seen.add(row.item)
	return {}
