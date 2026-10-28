import frappe
from frappe.utils import cint

USER_SET_FIELDS = ("major_colour", "set_colour")


def get_web_manual_items(manual_items, sizes):
	"""Rows for the /web manual bundle grid from fetch_manual_item_details output."""
	rows = []
	for detail in manual_items.values():
		rows.append(
			{
				"colour": detail.get("colour") or "",
				"major_colour": detail.get("major_colour") or "",
				"set_colour": detail.get("set_colour") or "",
				"shade": detail.get("shade") or "",
				"quantity": cint(detail.get("quantity")),
				"multipliers": {size: cint(detail.get(size)) for size in sizes},
			}
		)
	return rows


def build_manual_item_details(rows, sizes, colours, is_set_item, get_set_fields):
	"""Validate /web bundle rows like the Desk grid and shape them for save_manual_item_details."""
	if not isinstance(rows, list):
		frappe.throw("Bundle entries must be a row list")
	details = {}
	for index, row in enumerate(rows):
		label = f"Bundle Row {index + 1}"
		values = validate_manual_row(row, label, sizes, colours, is_set_item)
		detail = {
			"colour": values["colour"],
			"major_colour": values["major_colour"],
			"quantity": values["quantity"],
			"shade": values["shade"],
			"manual_index": index,
			**values["multipliers"],
		}
		if is_set_item:
			detail["set_colour"] = values["set_colour"]
		for field in get_set_fields(values["colour"]):
			fieldname = field["fieldname"]
			if fieldname not in USER_SET_FIELDS and field.get("default") is not None:
				detail[fieldname] = field["default"]
		details[index] = detail
	return details


def validate_manual_row(row, label, sizes, colours, is_set_item):
	if not isinstance(row, dict):
		frappe.throw(f"{label}: Bundle entry must be an object")
	values = {
		fieldname: str(row.get(fieldname) or "").strip()
		for fieldname in ("colour", "major_colour", "set_colour", "shade")
	}
	required = [("colour", "Enter Colour"), ("major_colour", "Enter Major Colour")]
	if is_set_item:
		required.append(("set_colour", "Enter Set Colour"))
	required.append(("shade", "Enter the Shade"))
	for fieldname, message in required:
		if not values[fieldname]:
			frappe.throw(f"{label}: {message}")
		if fieldname != "shade" and values[fieldname] not in colours:
			frappe.throw(f"{label}: Colour {values[fieldname]} is not available for this LaySheet")
	values["quantity"] = whole_number(row.get("quantity"), f"{label}: Quantity")
	if values["quantity"] <= 0:
		frappe.throw(f"{label}: Quantity should be greater than Zero")
	values["multipliers"] = get_multipliers(row.get("multipliers"), label, sizes)
	return values


def get_multipliers(multipliers, label, sizes):
	multipliers = multipliers if isinstance(multipliers, dict) else {}
	unknown = set(multipliers) - set(sizes)
	if unknown:
		frappe.throw(f"{label}: Unknown size {', '.join(sorted(unknown))}")
	values = {size: whole_number(multipliers.get(size), f"{label}: {size} multiplier") for size in sizes}
	if any(value < 0 for value in values.values()):
		frappe.throw(f"{label}: Negative Multiplier's are not Accepted")
	if not any(values.values()):
		frappe.throw(f"{label}: Enter the Multiplier for atleast one size")
	return values


def whole_number(value, label):
	if value is None or value == "":
		return 0
	try:
		number = float(value)
	except (TypeError, ValueError):
		frappe.throw(f"{label} must be a number")
	if not number.is_integer():
		frappe.throw(f"{label} must be a whole number")
	return int(number)
