const link = (fieldname, label, options) => ({ fieldname, label, fieldtype: "Link", options })
const date = (fieldname, label) => ({ fieldname, label, fieldtype: "Date", reqd: 1 })
const select = (fieldname, label, values, extra = {}) => ({ fieldname, label, fieldtype: "Select",
	options: ["", ...values].map(value => ({ value, label: value || "All" })), ...extra,
})

const ageingRanges = () => [30, 60, 90].map((value, index) => ({
	fieldname: `range${index + 1}`, label: `Ageing Range ${index + 1}`, fieldtype: "Int", default: value, reqd: 1,
}))
const purpose = values => ({ fieldname: "purpose", label: "Purpose", fieldtype: "Select",
	options: ["", ...values].map(value => ({ value, label: value || "All" })),
})

export function inspectionResultCellTone(fieldname, value) {
	if (!String(fieldname).includes("result")) return ""
	return { Pass: "success", Fail: "danger", Hold: "warning" }[value] || ""
}

export const deskReportConfig = {
	"quality-inspection-rft": {
		title: "Quality Inspection RFT", dateDefaults: "none", cellTone: inspectionResultCellTone,
		filters: [link("lot", "Lot", "SD YRP Lot"), link("item", "Item", "Item"),
			{ ...date("from_date", "From Date"), reqd: 0 }, { ...date("to_date", "To Date"), reqd: 0 },
			link("supplier", "Supplier", "Supplier"), select("result", "Result", ["Pass", "Fail", "Hold"])],
	},
	"purchase-order-itemwise": {
		title: "Purchase Order Itemwise", dateDefaults: "none",
		filters: [link("item", "Item", "Item"), link("supplier", "Supplier", "Supplier"),
			link("purchase_order", "Purchase Order", "Purchase Order"), link("delivery_location", "Delivery Location", "Supplier"),
			link("lot", "Lot", "SD YRP Lot"),
			select("status", "Status", ["Draft", "Ordered", "Cancelled", "Delivered", "Partially Delivered", "Partially Cancelled"]),
			select("open_status", "Open Status", ["Open", "Closed"], { default: "Open" }),
			select("docstatus", "Docstatus", ["0", "1", "2"]),
			select("date_based_on", "Date Filter Based On", ["Posting Date", "Delivery Date"]),
			{ fieldname: "from_date", label: "From Date", fieldtype: "Date", depends_on: "date_based_on" },
			{ fieldname: "to_date", label: "To Date", fieldtype: "Date", depends_on: "date_based_on" }],
	},
	"lot-consumption-report": {
		title: "Lot Consumption Report",
		filters: [{ ...link("lot", "Lot", "SD YRP Lot"), reqd: 1 }, date("start_date", "Start Date"),
			date("end_date", "End Date"), { ...link("item_group", "Item Group", "Item Group"), reqd: 1 }],
	},
	"dc-report": {
		title: "DC Report",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("lot", "Lot", "SD YRP Lot"),
			link("from_location", "From Location", "Supplier"), link("supplier", "Supplier", "Supplier")],
	},
	"jobwork-issued-items": {
		title: "Jobwork Issued Items",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("lot", "Lot", "SD YRP Lot"),
			link("from_location", "From Location", "Supplier"), link("supplier", "Supplier", "Supplier"), link("item", "Item", "Item")],
	},
	"non-jobwork-issued-items": {
		title: "Non Jobwork Issued Items",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), purpose(["Material Issue", "Send to Warehouse"]),
			link("lot", "Lot", "SD YRP Lot"), link("from_location", "From Location", "Supplier"), link("supplier", "Supplier", "Supplier"), link("item", "Item", "Item")],
	},
	"non-grn-received-items": {
		title: "Non-GRN Received Items",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), purpose(["Material Receipt", "Send to Warehouse"]),
			link("lot", "Lot", "SD YRP Lot"), link("received_location", "Received Location", "Supplier"), link("supplier", "Supplier", "Supplier"), link("item", "Item", "Item")],
	},
	"lot-wise-stock-ageing": {
		title: "Lot Wise Stock Ageing",
		filters: [date("to_date", "As On Date"), link("warehouse", "Warehouse", "Supplier"), link("lot", "Lot", "SD YRP Lot"),
			link("item", "Item Variant", "Item"), link("parent_item", "Item", "Item"), link("brand", "Brand", "Brand"), ...ageingRanges(),
			{ fieldname: "show_warehouse_wise_stock", label: "Show Warehouse-wise Stock", fieldtype: "Check", default: 0 }],
	},
	"stock-ageing": {
		title: "YRP Stock Ageing",
		filters: [date("to_date", "As On Date"), link("warehouse", "Warehouse", "Supplier"),
			link("item", "Item Variant", "Item"), link("parent_item", "Item", "Item"), ...ageingRanges(),
			{ fieldname: "show_warehouse_wise_stock", label: "Show Warehouse Wise Stock", fieldtype: "Check", default: 1 }],
	},
	"grn-report": {
		title: "GRN Report",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("lot", "Lot", "SD YRP Lot"), link("supplier", "Supplier", "Supplier"), link("delivery_location", "Delivery Location", "Supplier")],
	},
	"grn-summary": {
		title: "GRN Summary",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("supplier", "Supplier", "Supplier"), link("item", "Item", "Item"),
			{ fieldname: "only_show_stock_item", label: "Only Show Stock Item", fieldtype: "Check" },
			link("lot", "Lot", "SD YRP Lot"), link("delivery_location", "Delivery Location", "Supplier"),
			{ fieldname: "status", label: "Status", fieldtype: "Select", options: [{ value: "", label: "All" }, { value: "0", label: "Draft" }, { value: "1", label: "Submitted" }, { value: "2", label: "Cancelled" }] }],
	},
	"purchase-order-log": {
		title: "Purchase Order Log",
		filters: [link("purchase_order", "Purchase Order", "Purchase Order"), { fieldname: "po_date", label: "PO Date", fieldtype: "Date" }, link("supplier", "Supplier", "Supplier")],
	},
	"lot-purchase-summary": {
		title: "Lot Purchase Summary",
		filters: [link("lot", "Lot", "SD YRP Lot"), link("item", "Item Variant", "Item"), link("parent_item", "Item", "Item")],
	},
	"stock-entry-report": {
		title: "Stock Entry Report",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("item", "Item", "Item"), link("item_variant", "Item Variant", "Item"),
			link("from_warehouse", "From Warehouse", "Supplier"), link("to_warehouse", "To Warehouse", "Supplier"), link("lot", "Lot", "SD YRP Lot")],
	},
	"stock-reconciliation-report": {
		title: "Stock Reconciliation Report", dateDefaults: "previous-month",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("item", "Item", "Item"), link("item_variant", "Item Variant", "Item"),
			link("lot", "Lot", "SD YRP Lot"), link("supplier", "Supplier", "Supplier")],
	},
	"stock-update-report": {
		title: "Stock Update Report",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("item", "Item", "Item"), link("item_variant", "Item Variant", "Item"),
			link("warehouse", "Warehouse", "Supplier"), link("lot", "Lot", "SD YRP Lot")],
	},
	"item-conversion-report": {
		title: "Item Conversion Report", dateDefaults: "previous-month",
		filters: [date("from_date", "From Date"), date("to_date", "To Date"), link("lot", "Lot", "SD YRP Lot"),
			{ ...link("from_item", "From Item", "Item"), filters: { is_stock_item: 1 } },
			{ ...link("to_item", "To Item", "Item"), filters: { is_stock_item: 1 } }],
	},
	"finishing-inward-updates": {
		title: "Finishing Inward Updates", renderedExport: true,
		filters: [{ ...link("supplier", "Sewing Unit", "Supplier"), reqd: 1, filters: { is_company_location: 1 } }],
	},
}

export function deskReportQueryFilters(key, query = {}) {
	const values = {}
	for (const field of deskReportConfig[key].filters) {
		let value = query[field.fieldname]
		if (Array.isArray(value)) value = value[0]
		if (value == null) continue
		if (["Int", "Check"].includes(field.fieldtype)) {
			if (value === "" || !Number.isFinite(Number(value))) continue
			value = field.fieldtype === "Check" ? Number(Boolean(Number(value))) : Number(value)
		}
		values[field.fieldname] = value
	}
	return values
}

export function deskReportDefaults(key, today) {
	const [year, month, day] = today.split("-").map(Number)
	const monthly = deskReportConfig[key].dateDefaults === "previous-month"
	const lastDay = new Date(year, month - 1, 0).getDate()
	const previous = new Date(year, month - 2, monthly ? 1 : Math.min(day, lastDay))
	const isoDate = value => [value.getFullYear(), String(value.getMonth() + 1).padStart(2, "0"), String(value.getDate()).padStart(2, "0")].join("-")
	const fromDate = isoDate(previous)
	// Desk shifts the current month's end back one month, clamping its day.
	const toDate = monthly ? isoDate(new Date(year, month - 2, Math.min(new Date(year, month, 0).getDate(), lastDay))) : today
	return Object.fromEntries(deskReportConfig[key].filters.map(field => [field.fieldname,
		field.fieldname === "start_date" ? isoDate(new Date(year, month - 2, 1))
			: field.fieldname === "end_date" ? isoDate(new Date(year, month - 1, 0))
			: field.fieldname === "from_date" && deskReportConfig[key].dateDefaults !== "none" ? fromDate
			: field.fieldname === "to_date" && deskReportConfig[key].dateDefaults !== "none" ? toDate
			: field.default ?? (field.fieldtype === "Check" ? 0 : ""),
	]))
}

const grnDepartments = ["cutting", "fabric-store", "cut-panel-store", "accessory-store", "sewing", "finishing", "merch", "purchase"]
export function departmentDeskReports(department, capabilities, allowed = true) {
	if (!allowed || ![...grnDepartments, "accounts"].includes(department)) return []
	const keys = grnDepartments.includes(department) ? ["grn-report", "grn-summary", "dc-report", "stock-entry-report", "stock-reconciliation-report", "stock-update-report"] : []
	if (["purchase", "accessory-store", "fabric-store", "accounts"].includes(department)) {
		keys.push("jobwork-issued-items", "non-jobwork-issued-items", "non-grn-received-items", "lot-wise-stock-ageing", "stock-ageing")
	}
	if (["purchase", "accessory-store", "fabric-store", "cutting"].includes(department)) keys.push("item-conversion-report")
	if (department === "purchase") keys.push("purchase-order-log", "lot-purchase-summary")
	if (["purchase", "accounts"].includes(department)) keys.push("purchase-order-itemwise")
	if (["purchase", "fabric-store", "accessory-store", "accounts"].includes(department)) keys.push("lot-consumption-report")
	if (department === "sewing") keys.push("finishing-inward-updates")
	return keys.filter(value => capabilities?.[value.replaceAll("-", "_")]?.can_read).map(value => ({
		key: value.replaceAll("-", "_"), value, label: deskReportConfig[value].title, icon: "pi pi-table",
		componentProps: { reportKey: value }, props: { reportKey: value },
	}))
}

/** Desk report tabs of several departments, each report once. */
export function combinedDeskReports(departments, capabilities) {
	const tabs = departments.flatMap((department) => departmentDeskReports(department, capabilities))
	return tabs.filter((tab, index) => tabs.findIndex((other) => other.value === tab.value) === index)
}

export function selectReportTab(tabs, current, requested) {
	if (requested && tabs.some(tab => tab.value === requested)) return requested
	if (tabs.some(tab => tab.value === current)) return current
	return tabs[0]?.value || ""
}
