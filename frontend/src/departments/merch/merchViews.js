export const MERCH_ROUTES = {
	lots: "merch-lots",
	lotNew: "merch-lot-new",
	lot: "merch-lot",
	lotEdit: "merch-lot-edit",
	reports: "merch-reports",
	ipds: "merch-ipds",
	ipdNew: "merch-ipd-new",
	ipd: "merch-ipd",
	ipdEdit: "merch-ipd-edit",
	processCosts: "merch-process-costs",
	processCostNew: "merch-process-cost-new",
	processCost: "merch-process-cost",
	processCostEdit: "merch-process-cost-edit",
	productionOrders: "merch-production-orders",
	productionOrderNew: "merch-production-order-new",
	productionOrder: "merch-production-order",
	productionOrderEdit: "merch-production-order-edit",
	workOrders: "merch-work-orders",
	workOrderNew: "merch-work-order-new",
	workOrder: "merch-work-order",
	workOrderEdit: "merch-work-order-edit",
	billTrackings: "merch-bill-trackings",
	billTrackingNew: "merch-bill-tracking-new",
	billTracking: "merch-bill-tracking",
	billTrackingEdit: "merch-bill-tracking-edit",
	purchaseInvoices: "merch-purchase-invoices",
	purchaseInvoiceNew: "merch-purchase-invoice-new",
	purchaseInvoice: "merch-purchase-invoice",
	purchaseInvoiceEdit: "merch-purchase-invoice-edit",
}

export const MERCH_SECTION_ORDER = ["lots", "item_production_details", "production_orders", "work_orders", "process_costs", "bill_tracking", "purchase_invoices", "reports"]

export const IPD_LIST_PATH = "/merch/item-production-details"

export function merchLauncherItems() {
	return [
		{
			key: "lots",
			label: "Lot",
			description: "Order and box quantities, colour-wise entries, cloth program and PPO link.",
			icon: "pi pi-th-large",
			to: "/merch/lots",
		},
		{
			key: "item_production_details",
			label: "Item Production Detail",
			description: "Sizes, colours, packing, stitching, cutting and BOM for each style version.",
			icon: "pi pi-sliders-h",
			to: IPD_LIST_PATH,
		},
		{
			key: "production_orders",
			label: "Production Order",
			description: "Approve PPO requests, request changes and follow linked lots.",
			icon: "pi pi-file-edit",
			to: "/merch/production-orders",
		},
		{
			key: "work_orders",
			label: "Work Order",
			description: "Process work orders with deliverables, receivables and closing.",
			icon: "pi pi-briefcase",
			to: "/merch/work-orders",
		},
		{
			key: "process_costs",
			label: "Process Cost",
			description: "Supplier process rates by item and attribute, with approval.",
			icon: "pi pi-calculator",
			to: "/merch/process-costs",
		},
		{
			key: "bill_tracking",
			label: "Vendor Bill Tracking",
			description: "Assign and follow supplier bills from receipt to invoice.",
			icon: "pi pi-receipt",
			to: "/merch/bill-tracking",
		},
		{
			key: "purchase_invoices",
			label: "Purchase Invoice",
			description: "Supplier bills against GRNs, with approval and ERP sync.",
			icon: "pi pi-file",
			to: "/merch/purchase-invoices",
		},
		{
			key: "reports",
			label: "Reports",
			description: "Work In Progress, Inward Quantity, Work Order, Size-wise Stock, Multi CCR and PPO reports.",
			icon: "pi pi-chart-bar",
			to: "/merch/reports",
		},
	].sort((left, right) => MERCH_SECTION_ORDER.indexOf(left.key) - MERCH_SECTION_ORDER.indexOf(right.key))
}

export function visibleMerchLauncherItems(sections, items = merchLauncherItems()) {
	return items.filter((item) => sections?.[item.key]?.can_read)
}

export const IPD_LIST_COLUMNS = [
	"item",
	"version",
	"tech_pack_version",
	"pattern_version",
	"primary_item_attribute",
	"dependent_attribute",
	"approval_status",
]

export const IPD_STATUS_OPTIONS = ["Not Approved", "Approved"]

export function ipdPath(name) {
	return `${IPD_LIST_PATH}/${encodeURIComponent(String(name))}`
}

export function ipdEditPath(name) {
	return `${ipdPath(name)}/edit`
}

export function ipdRoute(name, extra = {}) {
	return { name: MERCH_ROUTES.ipd, params: { ipdId: String(name) }, ...extra }
}

export function ipdEditRoute(name, extra = {}) {
	return { name: MERCH_ROUTES.ipdEdit, params: { ipdId: String(name) }, ...extra }
}
