import frappe

FILTER_FIELDS = (
	("category", "Product Category", "Item", "product_category", "LinkField"),
	("product_season", "Product Season", "SD YRP Lot", "season", "LinkField"),
	("lot_status", "Lot Status", "SD YRP Lot", "status", "Select; required; Open"),
	("lot", "Lot", "SD YRP Lot", "name", "Ordered LinkField chips + Paste"),
	("item", "Item", "SD YRP Lot", "item", "Ordered LinkField chips + Paste"),
	("from_date", "Lot From Date", "SD YRP Lot", "creation", "DateField; paired dates"),
	("to_date", "Lot To Date", "SD YRP Lot", "creation", "DateField; inclusive day"),
	("process_list", "Processes", "YRP IPD Process", "process_name", "Ordered LinkField chips"),
)

EXCLUDED = (
	("columnFilters", "Per-column text filters", "ReportShell has no column filters; CSV supports spreadsheet filtering."),
	("drill_down", "Inhouse Quantity", "Target report is deferred; process cells stay unlinked."),
)


def field_inventory():
	"""Generate the reference UI inventory from the site's effective metadata."""
	rows = []
	for key, label, doctype, fieldname, widget in FILTER_FIELDS:
		meta = frappe.get_meta(doctype)
		field = meta.get_field(fieldname)
		if fieldname in ("creation", "name"):
			assert fieldname in meta.get_valid_columns(), f"Missing {doctype}.{fieldname}"
			field = (frappe._dict(fieldtype="Link", options=doctype) if fieldname == "name"
				else frappe._dict(fieldtype="Datetime", options=None))
		assert field, f"Missing {doctype}.{fieldname}"
		rows.append({"key": key, "label": label, "status": "in /web ✅", "source": f"{doctype}.{fieldname}",
			"fieldtype": field.fieldtype, "options": field.options, "widget": widget})
	rows.extend({"key": key, "label": label, "status": "excluded", "reason": reason} for key, label, reason in EXCLUDED)
	rows.extend({"key": key, "label": label, "status": "in /web ✅", "widget": widget} for key, label, widget in (
		("generate", "Show Report", "ReportShell Generate"), ("paste", "Paste", "Lot / Item paste dialog"),
		("paste_target", "Paste into", "Select: Lot / Item"), ("paste_names", "Names", "Textarea; TSV / newline"),
		("report", "Report", "Tab / Select; URL query report=work-in-progress"),
		("excel", "Excel", "Download CSV (current rows, Excel compatible) + Copy Report"),
	))
	return rows
