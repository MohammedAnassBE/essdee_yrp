const link = (fieldname, label, options) => ({ fieldname, label, fieldtype: "Link", options })
const date = (fieldname, label) => ({ fieldname, label, fieldtype: "Date", reqd: 1 })

export const deskReportConfig = {
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
	"finishing-inward-updates": {
		title: "Finishing Inward Updates",
		filters: [{ ...link("supplier", "Sewing Unit", "Supplier"), reqd: 1, filters: { is_company_location: 1 } }],
	},
}

export function deskReportDefaults(key, today) {
	const [year, month, day] = today.split("-").map(Number)
	const lastDay = new Date(year, month - 1, 0).getDate()
	const previous = new Date(year, month - 2, Math.min(day, lastDay))
	const fromDate = [previous.getFullYear(), String(previous.getMonth() + 1).padStart(2, "0"), String(previous.getDate()).padStart(2, "0")].join("-")
	return Object.fromEntries(deskReportConfig[key].filters.map(field => [field.fieldname,
		field.fieldname === "from_date" ? fromDate : field.fieldname === "to_date" ? today : field.fieldtype === "Check" ? 0 : "",
	]))
}

const grnDepartments = ["cutting", "fabric-store", "cut-panel-store", "accessory-store", "sewing", "finishing", "merch", "purchase"]
export function departmentDeskReports(department, capabilities, allowed = true) {
	if (!allowed || !grnDepartments.includes(department)) return []
	const keys = ["grn-report", "grn-summary"]
	if (department === "purchase") keys.push("purchase-order-log", "lot-purchase-summary")
	if (department === "sewing") keys.push("finishing-inward-updates")
	return keys.filter(value => capabilities?.[value.replaceAll("-", "_")]?.can_read).map(value => ({
		key: value.replaceAll("-", "_"), value, label: deskReportConfig[value].title, icon: "pi pi-table",
		componentProps: { reportKey: value }, props: { reportKey: value },
	}))
}
