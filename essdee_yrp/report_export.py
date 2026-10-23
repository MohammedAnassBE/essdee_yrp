import frappe
from frappe import _
from frappe.desk.query_report import add_total_row, build_xlsx_data, format_fields
from frappe.desk.query_report import run as run_query_report
from frappe.desk.utils import get_csv_bytes, pop_csv_params, provide_binary_file
from frappe.permissions import can_export
from frappe.utils import cint
from frappe.utils.xlsxutils import handle_html, make_xlsx
from yrp.web_reports.access import check_report_access
from yrp.web_reports.background import needs_background
from yrp.web_reports.filters import authorize_filters
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.link_columns import get_linked_values
from yrp.web_reports.registry import get_web_report

FILE_FORMATS = ("Excel", "CSV")
CELL_TYPES = (str, int, float, bool, type(None))


@frappe.whitelist()
def get_export_permission(report_key=None, doctype=None) -> bool:
	"""Mirror Desk's Export menu condition: report access plus export on the ref doctype."""
	try:
		return bool(can_export(get_export_doctype(report_key, doctype)))
	except frappe.PermissionError:
		return False


def get_export_doctype(report_key=None, doctype=None) -> str:
	if not report_key:
		if not doctype or not frappe.db.exists("DocType", doctype):
			frappe.throw(_("A valid export doctype is required."))
		return doctype
	entry = get_web_report(report_key)
	check_report_access(entry)
	if entry.report:
		return frappe.get_cached_value("Report", entry.report, "ref_doctype")
	if not entry.permission_doctypes:
		frappe.throw(_("Web report {0} has no export doctype.").format(report_key))
	return entry.permission_doctypes[0]


@frappe.whitelist(methods=["POST"])
def export_web_report(report_key, columns, filters=None, file_format_type="Excel", include_filters=0, applied_filters=None, csv_delimiter=",", csv_quoting=2, csv_decimal_sep=".", visible_idx=None):
	"""Re-run a Desk-backed /web report like Desk's export_query, keeping the picked columns."""
	entry = get_web_report(report_key)
	if entry.kind != "frappe_report":
		frappe.throw(_("Web report {0} is not a Desk report.").format(report_key))
	can_export(get_export_doctype(report_key), raise_exception=True)
	validate_file_format(file_format_type)
	filters = authorize_filters(entry.filters, filters)
	data = frappe._dict(get_export_data(entry, filters))
	if not data.columns:
		frappe.throw(_("No data to export. You can try changing the filters of your report."))
	keep_visible_rows(data, frappe.parse_json(visible_idx))
	data.columns, data.result = get_picked_table(entry, data, frappe.parse_json(columns) or [])
	data.update(report_name=entry.report, filters=filters, applied_filters=frappe.parse_json(applied_filters))
	format_fields(data, file_format_type)
	rows, column_widths, styles = build_xlsx_data(data, include_filters=include_filters, build_styles=file_format_type == "Excel")
	csv_options = {"csv_delimiter": csv_delimiter, "csv_quoting": csv_quoting, "csv_decimal_sep": csv_decimal_sep}
	write_report_file(entry.report, rows, file_format_type, csv_options, column_widths, styles)


@frappe.whitelist(methods=["POST"])
def export_report_rows(title, rows, report_key=None, doctype=None, file_format_type="Excel", include_filters=0, applied_filters=None, csv_delimiter=",", csv_quoting=2, csv_decimal_sep="."):
	"""Export the rows a custom /web report rendered, after the same export permission check."""
	can_export(get_export_doctype(report_key, doctype), raise_exception=True)
	validate_file_format(file_format_type)
	rows = validate_rows(frappe.parse_json(rows))
	filter_rows = get_filter_rows(frappe.parse_json(applied_filters)) if cint(include_filters) else []
	csv_options = {"csv_delimiter": csv_delimiter, "csv_quoting": csv_quoting, "csv_decimal_sep": csv_decimal_sep}
	write_report_file(title, filter_rows + rows, file_format_type, csv_options)


def get_export_data(entry, filters) -> dict:
	"""Export a background-sized report from its finished YRP Report Job instead of re-running it here."""
	if not needs_background(entry, filters):
		return run_query_report(entry.report, filters, ignore_prepared_report=True, are_default_filters=False)
	envelope = run_web_report(entry.key, filters)
	if envelope["job"]["status"] != "Completed":
		frappe.throw(_("This report is still being prepared in the background. Export again once it is ready."))
	return envelope


def keep_visible_rows(data, visible_idx) -> None:
	"""Keep the inline-filtered rows and rebuild the total row, like Desk's export_query visible_idx."""
	if visible_idx is None:
		return
	if not isinstance(visible_idx, list) or not all(isinstance(index, int) for index in visible_idx):
		frappe.throw(_("Visible rows must be a list of row numbers."))
	result = [data.result[index] for index in visible_idx if 0 <= index < len(data.result)]
	data.result = add_total_row(result, data.columns) if cint(data.get("add_total_row")) else result


def get_picked_table(entry, data, picked_columns) -> tuple[list[dict], list[dict]]:
	source_columns = [frappe._dict(column) for column in data.columns]
	by_fieldname = {column.fieldname: column for column in source_columns}
	fieldnames = [column.fieldname for column in source_columns]
	result = [row if isinstance(row, dict) else dict(zip(fieldnames, row, strict=True)) for row in data.result or []]
	columns = []
	for index, picked in enumerate(picked_columns):
		if picked.get("kind") == "linked":
			columns.append(frappe._dict(fieldname=f"__linked_{index}", label=picked.get("label"), fieldtype=picked.get("fieldtype") or "Data", width=picked.get("width") or 120, linked=picked))
			continue
		if picked.get("fieldname") not in by_fieldname:
			frappe.throw(_("Column {0} is not in report {1}.").format(picked.get("label") or picked.get("fieldname"), entry.report))
		columns.append({**by_fieldname[picked["fieldname"]], "label": picked.get("label") or by_fieldname[picked["fieldname"]].label})
	add_linked_values(entry, columns, result)
	return columns, result


def add_linked_values(entry, columns, result) -> None:
	linked_columns = [column for column in columns if column.get("linked")]
	if not linked_columns:
		return
	requests = [{
		"source_column": column.linked["source_column"],
		"fields": [column.linked["target_field"]],
		"names": sorted({row.get(column.linked["source_column"]) for row in result if row.get(column.linked["source_column"])}),
	} for column in linked_columns]
	values = get_linked_values(entry.key, requests)
	for column in linked_columns:
		source, target = column.linked["source_column"], column.linked["target_field"]
		for row in result:
			row[column.fieldname] = (values.get(source, {}).get(row.get(source)) or {}).get(target)
		del column["linked"]


def get_filter_rows(applied_filters) -> list[list]:
	rows = [[str(label), ", ".join(map(str, value)) if isinstance(value, list) else str(value)] for label, value in (applied_filters or {}).items() if value]
	return [*rows, []] if rows else []


def validate_rows(rows) -> list[list]:
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("There are no report rows to export."))
	for row in rows:
		if not isinstance(row, list) or not all(isinstance(value, CELL_TYPES) for value in row):
			frappe.throw(_("Each export row must be a list of plain values."))
	return rows


def validate_file_format(file_format_type) -> None:
	if file_format_type not in FILE_FORMATS:
		frappe.throw(_("Only CSV and Excel formats are supported for export"), title=_("Unsupported file format: {0}").format(file_format_type))


def write_report_file(title, rows, file_format_type, csv_options, column_widths=None, styles=None) -> None:
	if file_format_type == "CSV":
		csv_rows = [[handle_html(value) if isinstance(value, str) else value for value in row] for row in rows]
		provide_binary_file(title, "csv", get_csv_bytes(csv_rows, pop_csv_params(csv_options)))
		return
	provide_binary_file(title, "xlsx", make_xlsx(rows, title, column_widths=column_widths, styles=styles).getvalue())
