"""Authoritative Sewing reports: batch facts once, then assemble in memory."""

from collections import defaultdict
from datetime import date as date_type

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate
from yrp.attribute_links import value as attribute_value
from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import get_ipd_primary_values

from essdee_yrp.sewing.config import get_sewing_input_configuration
from essdee_yrp.sewing.entry import _variant_attributes

DATE_FIELDS = {
	"FI Date": "fi_date",
	"Input Date": "input_date",
	"Last Sewing Output": "last_output_date",
	"Total Running Days": "running_days",
}
READINESS_FIELDS = {
	"Ready for Checking": "ready_for_checking",
	"Ready for AQL": "ready_for_aql",
	"Ready for Pre final": "ready_for_pre_final",
	"Ready for Final Inspection": "ready_for_final_inspection",
}


def _report_plans(supplier, *, open_only=False):
	from essdee_yrp.sewing.read_models import _plans

	frappe.has_permission("SD YRP Sewing Plan", "read", throw=True)
	frappe.has_permission("SD YRP Sewing Plan", "report", throw=True)
	plans = _plans(supplier)
	names = list({row.work_order for row in plans if row.work_order})
	work_orders = {}
	if names:
		filters = {"name": ["in", names]}
		if open_only:
			filters["open_status"] = "Open"
		else:
			filters["supplier"] = cstr(supplier).strip()
		work_orders = {
			row.name: row
			for row in frappe.get_list(
				"YRP Work Order",
				filters=filters,
				fields=["name", "open_status"],
				limit=0,
			)
		}
	# Status scopes the supplier on the plan, as MRP does. DPR retains its owner check.
	plans = [row for row in plans if row.work_order in work_orders or (not open_only and not row.work_order)]
	# MRP's plan scan follows its primary key; get_list otherwise defaults to modified desc.
	return sorted(plans, key=lambda row: row.name) if open_only else plans


def _snapshot(
	plans, *, from_date=None, to_date=None, work_station=None, input_type=None, status_order=False
):
	from essdee_yrp.sewing.read_models import _details, _metadata

	plan_map = {row.name: row for row in plans}
	orders, entries = [], []
	if plans:
		orders = frappe.get_all(
			"SD YRP Sewing Plan Order Detail",
			filters={"parent": ["in", list(plan_map)], "parenttype": "SD YRP Sewing Plan"},
			fields=[
				"parent",
				"item_variant",
				"set_combination",
				"quantity",
				"pre_final",
				"final_inspection",
				"fi_date",
			],
			order_by="name asc" if status_order else None,
			limit=0,
		)
		frappe.has_permission("SD YRP Sewing Plan Entry Detail", "read", throw=True)
		filters = {"sewing_plan": ["in", list(plan_map)]}
		if from_date is not None:
			filters["entry_date"] = ["between", [from_date, to_date]]
		if work_station:
			filters["work_station"] = work_station
		if input_type:
			filters["input_type"] = input_type
		entries = frappe.get_list(
			"SD YRP Sewing Plan Entry Detail",
			filters=filters,
			fields=["name", "sewing_plan", "input_type", "received_type", "work_station", "entry_date"],
			order_by="name asc" if status_order else "entry_date asc, name asc",
			limit=0,
		)
	if status_order and entries:
		details = frappe.get_all(
			"SD YRP Sewing Plan Detail",
			filters={
				"parent": ["in", [row.name for row in entries]],
				"parenttype": "SD YRP Sewing Plan Entry Detail",
			},
			fields=["parent", "item_variant", "set_combination", "quantity"],
			order_by="name asc",
			limit=0,
		)
	else:
		details = _details(entries)
	lots, ipds = _metadata(plans) if plans else ({}, {})
	return frappe._dict(
		plans=plan_map,
		orders=orders,
		entries=entries,
		details=details,
		lots=lots,
		ipds=ipds,
	)


def _bucket_context(snapshot, plan, row, attributes):
	from essdee_yrp.sewing.read_models import _bucket

	lot = snapshot.lots.get(plan.lot)
	ipd = snapshot.ipds.get(lot.production_detail) if lot else None
	if not ipd:
		frappe.throw(_("Lot {0} has no production detail for the Sewing report.").format(plan.lot))
	bucket, size = _bucket(row, ipd, attributes)
	return ipd, bucket, size


def _stage_label(stage, received_type, settings, default_received_type):
	if not received_type or received_type == default_received_type:
		return stage
	if stage == settings.type_wise_diff_summary:
		return received_type
	return f"{stage} {received_type}"


def _quantity_key(label):
	return label.lower().replace(" ", "_")


def status_summary(supplier):
	plans = _report_plans(supplier, open_only=True)
	if not plans:
		return {"header1": [], "header2": [], "header3": [], "data": []}
	snapshot = _snapshot(plans, status_order=True)
	settings = frappe.get_cached_doc("SD YRP MRP Settings")
	configuration = get_sewing_input_configuration()
	default_received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	stages = [row.input_type for row in configuration]
	for field in (
		"sewing_input_qty_type",
		"sewing_line_output_type",
		"type_wise_diff_summary",
		"sewing_plan_inspection_type",
	):
		if settings.get(field) not in stages:
			label = settings.meta.get_field(field).label
			frappe.throw(_("Configure {0} as a Sewing Input Type in MRP Settings.").format(_(label)))
	columns = [
		(
			row.received_type
			if row.input_type == settings.type_wise_diff_summary and row.received_type != default_received_type
			else row.input_type
		)
		for row in settings.sewing_plan_status_summary
	]
	work_orders = list({row.work_order for row in plans})
	# DC/GRN lifecycle hooks rebuild garment-piece projections here. Raw stock
	# deliverables can include multiple panels and accessories with other UOMs.
	calculated = (
		frappe.get_all(
			"YRP Work Order Calculated Item",
			filters={"parent": ["in", work_orders], "parenttype": "YRP Work Order"},
			fields=["parent", "item_variant", "set_combination", "delivered_quantity", "received_qty"],
			order_by="name asc",
			limit=0,
		)
		if work_orders
		else []
	)
	attributes = _variant_attributes(
		{row.item_variant for row in [*snapshot.orders, *snapshot.details, *calculated] if row.item_variant}
	)
	data, columns = _assemble_status(
		snapshot, calculated, attributes, settings, default_received_type, columns
	)
	headers = [
		"Order Qty",
		"Delivered Qty",
		*columns,
		"Pre Final",
		"Final Inspection",
		"GRN Qty",
		"GRN Pending",
		"Line Stock",
		"Stock",
	]
	totals = {"is_total": True}
	for header in headers:
		totals[header] = sum(flt(row.get(header)) for row in data)
		totals[_quantity_key(header)] = totals[header]
	totals["Checking Stock"] = totals["checking_stock"] = totals["Stock"]
	return {
		"header1": ["Item", "SD YRP Lot", "Colour", "Part", *DATE_FIELDS],
		"header2": headers,
		"header3": list(READINESS_FIELDS),
		"data": [totals, *data] if data else [],
	}


def _assemble_status(snapshot, calculated, attributes, settings, default_received_type, columns):
	columns = list(columns)
	groups = {}
	dates = defaultdict(lambda: defaultdict(list))
	checking_totals = defaultdict(float)
	calculated_by_wo, orders_by_plan, entries_by_plan, details_by_entry = (defaultdict(list) for _ in range(4))
	for row in calculated:
		calculated_by_wo[row.parent].append(row)
	for row in snapshot.orders:
		orders_by_plan[row.parent].append(row)
	for entry in snapshot.entries:
		entries_by_plan[entry.sewing_plan].append(entry)
	for row in snapshot.details:
		details_by_entry[row.parent].append(row)

	def group(plan, row):
		ipd, bucket, _size = _bucket_context(snapshot, plan, row, attributes)
		variant = attributes.get(row.item_variant, {})
		non_size = tuple(sorted(v for k, v in variant.items() if k != ipd.primary_item_attribute)) or None
		combination = update_if_string_instance(row.set_combination) or {}
		key = (plan.item, plan.lot, non_size, tuple(sorted(combination.items())))
		# MRP always shows both variant and major colour for a set, including equal colours.
		colour = (
			f"{variant.get(ipd.packing_attribute, '')} ({combination.get('major_colour', '')})"
			if ipd.is_set_item
			else combination.get("major_colour", "")
		)
		return key, groups.setdefault(
			key,
			{
				"item": plan.item,
				"lot": plan.lot,
				"sewing_plan": plan.name,
				"work_order": plan.work_order,
				"colour": colour,
				"part": attribute_value(bucket["part"]),
				"work_order_status": "Open",
			},
		)

	# Dict insertion order is visible in MRP: each plan's calculated items first,
	# then its order and entry facts. Group identity deliberately excludes plan/WO.
	for plan in snapshot.plans.values():
		for row in calculated_by_wo[plan.work_order]:
			_key, values = group(plan, row)
			for label, field in (("Delivered Qty", "delivered_quantity"), ("GRN Qty", "received_qty")):
				values[label] = flt(values.get(label)) + flt(row.get(field))
		for row in orders_by_plan[plan.name]:
			key, values = group(plan, row)
			for header, field in (
				("Order Qty", "quantity"),
				("Pre Final", "pre_final"),
				("Final Inspection", "final_inspection"),
			):
				values[header] = flt(values.get(header)) + flt(row.get(field))
			if row.fi_date:
				dates[key]["fi_date"].append(getdate(row.fi_date))
		for entry in entries_by_plan[plan.name]:
			for row in details_by_entry[entry.name]:
				key, values = group(plan, row)
				label = _stage_label(entry.input_type, entry.received_type, settings, default_received_type)
				values[label] = flt(values.get(label)) + flt(row.quantity)
				if entry.input_type == settings.type_wise_diff_summary:
					checking_totals[key] += flt(row.quantity)
				if entry.entry_date:
					if entry.input_type == settings.sewing_input_qty_type:
						dates[key]["input_date"].append(getdate(entry.entry_date))
					if entry.input_type == settings.sewing_line_output_type:
						dates[key]["last_output_date"].append(getdate(entry.entry_date))
	for key, values in groups.items():
		line = flt(values.get(settings.sewing_line_output_type))
		checking = checking_totals[key]
		aql = flt(values.get(settings.sewing_plan_inspection_type))
		values["Line Stock"] = line - flt(values.get(settings.sewing_input_qty_type))
		values["Stock"] = values["Checking Stock"] = values["checking_stock"] = checking - line
		values["GRN Pending"] = line - flt(values.get("GRN Qty"))
		for name, aggregate in (("fi_date", min), ("input_date", min), ("last_output_date", max)):
			values[name] = aggregate(dates[key][name]) if dates[key][name] else None
		values["running_days"] = (
			(values["last_output_date"] - values["input_date"]).days
			if values["last_output_date"] and values["input_date"]
			else None
		)
		accepted_checking = flt(values.get(settings.type_wise_diff_summary))
		pre_final = flt(values.get("Pre Final"))
		final = flt(values.get("Final Inspection"))
		# Match MRP's quantity guards before filling readiness. An upstream
		# quantity alone (or an observed zero entry) leaves the cell blank.
		for label, source, completed, underway, started in (
			("Ready for Checking", line, checking, "Under Checking", line and checking),
			("Ready for AQL", accepted_checking, aql, "Under AQL", accepted_checking and aql),
			("Ready for Pre final", aql, pre_final, "Under Pre Final", aql and pre_final > 0),
			(
				"Ready for Final Inspection",
				pre_final,
				final,
				"Under Final Inspection",
				final > 0,
			),
		):
			status = (underway if source > completed else "Completed") if started else ""
			values[label] = values[READINESS_FIELDS[label]] = status
		for label, field in DATE_FIELDS.items():
			values[label] = values[field]
		for label in [
			"Order Qty",
			"Delivered Qty",
			*columns,
			"Pre Final",
			"Final Inspection",
			"GRN Qty",
			"GRN Pending",
			"Line Stock",
			"Checking Stock",
		]:
			values[label] = flt(values.get(label))
			values[_quantity_key(label)] = values[label]
	return (
		list(groups.values()),
		columns,
	)


def _report_date(value, label):
	"""Require an explicit date without Frappe's empty-input or zero-date fallback."""
	title = _("Invalid DPR Date")
	if value is None or (isinstance(value, str) and not value.strip()):
		frappe.throw(_("{0} is required.").format(_(label)), title=title)
	parsed = None
	if isinstance(value, str | date_type):
		previous_mute = frappe.flags.mute_messages
		try:
			# Replace parser errors with one plain, field-specific business message.
			frappe.flags.mute_messages = True
			parsed = getdate(value)
		except frappe.ValidationError, ValueError, TypeError, OverflowError:
			pass
		finally:
			frappe.flags.mute_messages = previous_mute
	if parsed is None:
		frappe.throw(_("Enter a valid {0}.").format(_(label)), title=title)
	return parsed


def daily_dpr(supplier, dpr_date, work_station=None, input_type=None):
	plans = _report_plans(supplier)
	date = _report_date(dpr_date, "DPR Date")
	snapshot = _snapshot(
		plans, from_date=date, to_date=date, work_station=work_station, input_type=input_type
	)
	return _dpr_reports(snapshot, [date])[0]


def dpr_summary(supplier, from_date, to_date, work_station=None, input_type=None):
	plans = _report_plans(supplier)
	start = _report_date(from_date, "From Date")
	end = _report_date(to_date, "To Date")
	if start > end:
		frappe.throw(_("From Date cannot be after To Date."))
	snapshot = _snapshot(
		plans, from_date=start, to_date=end, work_station=work_station, input_type=input_type
	)
	dates = sorted({getdate(row.entry_date) for row in snapshot.entries})
	reports = _dpr_reports(snapshot, dates)
	pending = {}
	for report in reports:
		for row in report["pending_fi"]:
			pending[(row["lot"], row["colour"], row["part"])] = row
	return {"reports": reports, "pending_fi": list(pending.values()), **_blocking_contract(bool(pending))}


def _blocking_contract(blocked):
	return {
		"status": "pending_fi" if blocked else "success",
		"blocked": blocked,
		"message": _("Set FI dates for the listed Lots, Colours and Parts to generate this report.")
		if blocked
		else "",
	}


def _dpr_reports(snapshot, dates):
	attributes = _variant_attributes(
		{row.item_variant for row in [*snapshot.orders, *snapshot.details] if row.item_variant}
	)
	primary_values = {ipd.name: get_ipd_primary_values(ipd.name) for ipd in snapshot.ipds.values()}
	headers = list(
		dict.fromkeys(
			[
				*[row.input_type for row in get_sewing_input_configuration()],
				*[row.input_type for row in snapshot.entries],
			]
		)
	)
	return _assemble_dpr(snapshot, dates, attributes, primary_values, headers)


def _assemble_dpr(snapshot, dates, attributes, primary_values, headers):
	entry_map = {row.name: row for row in snapshot.entries}
	by_date = defaultdict(list)
	plans_by_date = defaultdict(set)
	for entry in snapshot.entries:
		plans_by_date[getdate(entry.entry_date)].add(entry.sewing_plan)
	for row in snapshot.details:
		by_date[getdate(entry_map[row.parent].entry_date)].append(row)
	orders = defaultdict(list)
	for row in snapshot.orders:
		orders[row.parent].append(row)
	reports = []
	for date in dates:
		data = {}
		plan_names = plans_by_date[date]
		pending = {}
		for plan_name in sorted(plan_names):
			plan = snapshot.plans[plan_name]
			for row in orders[plan_name]:
				if row.fi_date:
					continue
				_ipd, bucket, _size = _bucket_context(snapshot, plan, row, attributes)
				key = (plan.lot, bucket["key"], attribute_value(bucket["part"]))
				pending[key] = {"lot": key[0], "colour": key[1], "part": key[2]}
		for row in by_date[date]:
			entry = entry_map[row.parent]
			plan = snapshot.plans[entry.sewing_plan]
			ipd, bucket, size = _bucket_context(snapshot, plan, row, attributes)
			lot_data = data.setdefault(entry.input_type, {}).setdefault(
				plan.lot,
				{
					"details": {},
					"is_set_item": ipd.is_set_item,
					"pack_attr": ipd.packing_attribute,
					"set_attr": ipd.set_item_attribute,
					"item": plan.item,
					"primary_values": primary_values[ipd.name],
				},
			)
			group = (
				lot_data["details"]
				.setdefault(entry.work_station or "-", {})
				.setdefault(entry.received_type or "-", {})
				.setdefault(
					bucket["key"],
					{
						"values": {},
						"part": attribute_value(bucket["part"]),
						"colour": bucket["key"],
						"variant_colour": bucket["variant_colour"],
						"set_combination": bucket["set_combination"],
						"total": 0,
					},
				)
			)
			group["values"][size] = flt(group["values"].get(size)) + flt(row.quantity)
			group["total"] += flt(row.quantity)
		reports.append(
			{
				"date": date.isoformat(),
				"headers": headers,
				"dpr_data": {} if pending else data,
				"pending_fi": list(pending.values()),
				**_blocking_contract(bool(pending)),
			}
		)
	return reports
