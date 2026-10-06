"""Version boundary and qualification helpers for the P0 cloth execution flow."""

import frappe
from frappe import _
from frappe.utils import cint

from essdee_yrp.fabric_chain import get_fabric_steps
from essdee_yrp.fabric_ipd import FABRIC_COLOUR_ATTRIBUTE, FABRIC_DIA_ATTRIBUTE

CLOTH_EXECUTION_VERSION = 1


def get_supported_execution_route(ipd_doc):
	"""Return the guarded Knitting -> Dyeing -> identity-Washing prefix."""
	if not ipd_doc:
		return None
	settings = frappe.get_cached_doc("SD YRP IPD Settings")
	steps = get_fabric_steps(ipd_doc)
	if len(steps) < 3:
		return None

	knitting, dyeing, washing = steps[:3]
	if (
		knitting.get("position") != 0
		or knitting.get("process_name") != settings.get("default_knitting_process")
		or knitting.get("shape") != "conversion"
	):
		return None
	if dyeing.get("position") != 1 or not _is_colour_dyeing_step(
		dyeing, settings.get("default_dyeing_process")
	):
		return None
	if washing.get("position") != 2 or washing.get("shape") != "identity":
		return None

	return {"knitting": knitting, "dyeing": dyeing, "washing": washing}


def _is_colour_dyeing_step(step, default_dyeing_process):
	shape = step.get("shape")
	attribute = step.get("attribute")
	if shape == "swap" and attribute == FABRIC_COLOUR_ATTRIBUTE:
		return True
	if shape == "multi_swap" and FABRIC_COLOUR_ATTRIBUTE in (attribute or []):
		return True
	# Old Process masters can lack shape metadata. Never use this fallback for
	# an explicit non-colour transformation such as Compacting/Dia change.
	if step.get("process_name") != default_dyeing_process:
		return False
	if shape == "swap" and attribute and attribute != FABRIC_COLOUR_ATTRIBUTE:
		return False
	if shape == "multi_swap" and attribute and FABRIC_COLOUR_ATTRIBUTE not in attribute:
		return False
	return attribute != FABRIC_DIA_ATTRIBUTE


def stamp_cloth_execution_version(doc, method=None):
	"""Stamp only newly inserted Work Orders in the supported route prefix."""
	del method
	if (
		cint(doc.get("cloth_execution_version"))
		or doc.get("is_rework")
		or not doc.get("production_detail")
	):
		return
	ipd = frappe.get_cached_doc("YRP Item Production Detail", doc.production_detail)
	route = get_supported_execution_route(ipd)
	if route and doc.get("process_name") in {row["process_name"] for row in route.values()}:
		doc.cloth_execution_version = CLOTH_EXECUTION_VERSION


def get_row_execution_parameters(row):
	value = row.get("additional_parameters") if row else None
	if isinstance(value, dict):
		return value
	if not value:
		return {}
	try:
		value = frappe.parse_json(value)
	except (TypeError, ValueError):
		return {}
	return value if isinstance(value, dict) else {}


def has_fabric_execution_key(row):
	return bool(get_row_execution_parameters(row).get("fabric_execution_key"))


def resolve_downstream_execution_version(work_order, source_rows, *, first_calculation):
	"""Close the legacy/versioned boundary before writing calculated rows."""
	version = cint(work_order.get("cloth_execution_version"))
	keyed = [has_fabric_execution_key(row) for row in (source_rows or [])]
	if not version:
		if any(keyed):
			frappe.throw(
				_("A legacy Work Order cannot consume a versioned cloth execution source.")
			)
		return 0
	if not keyed:
		return version
	if any(keyed) and not all(keyed):
		frappe.throw(
			_("Cloth source selection cannot contain mixed keyed and legacy rows.")
		)
	if all(keyed):
		return CLOTH_EXECUTION_VERSION
	if first_calculation:
		work_order.cloth_execution_version = 0
		return 0
	frappe.throw(
		_("A versioned Work Order cannot be recalculated from legacy cloth sources.")
	)


def is_versioned_cloth_work_order(doc_or_name):
	if isinstance(doc_or_name, str):
		version = frappe.db.get_value("YRP Work Order", doc_or_name, "cloth_execution_version")
	else:
		version = doc_or_name.get("cloth_execution_version") if doc_or_name else 0
	return cint(version) == CLOTH_EXECUTION_VERSION


def qualifies_cloth_transaction(doc):
	"""Return true only for saved keyed documents in the supported route."""
	work_order = _get_transaction_work_order(doc)
	if not work_order or not is_versioned_cloth_work_order(work_order):
		return False
	if not (work_order.get("production_detail") and work_order.get("process_name")):
		return False
	ipd = frappe.get_cached_doc("YRP Item Production Detail", work_order.production_detail)
	route = get_supported_execution_route(ipd)
	if not route or work_order.process_name not in {
		row["process_name"] for row in route.values()
	}:
		return False
	rows = _transaction_execution_rows(doc, work_order)
	return bool(rows and all(has_fabric_execution_key(row) for row in rows))


def _get_transaction_work_order(doc):
	if not doc:
		return None
	if doc.doctype == "YRP Work Order":
		return doc
	name = None
	if doc.doctype == "YRP Delivery Challan":
		name = doc.get("work_order")
	elif doc.doctype == "YRP Goods Received Note" and doc.get("against") == "YRP Work Order":
		name = doc.get("against_id")
	if not name:
		return None
	return frappe.get_cached_doc("YRP Work Order", name)


def _transaction_execution_rows(doc, work_order):
	if doc.doctype == "YRP Work Order":
		return [
			row
			for row in (doc.get("deliverables") or []) + (doc.get("receivables") or [])
			if row.get("is_calculated")
		]
	rows = doc.get("items") or []
	if rows and all(row.meta.get_field("additional_parameters") for row in rows):
		return rows
	# GRN rows do not universally expose additional_parameters. Resolve their
	# immutable WO child references instead of inventing a duplicate field.
	children = {
		row.name: row
		for row in (work_order.get("deliverables") or []) + (work_order.get("receivables") or [])
	}
	return [children[row.get("ref_docname")] for row in rows if row.get("ref_docname") in children]
