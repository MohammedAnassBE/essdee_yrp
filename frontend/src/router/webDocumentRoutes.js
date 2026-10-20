const recordRoutes = {
	"Item": (name) => `/web/purchase/items/${encodeURIComponent(name)}`,
	"YRP Production Order": (name) => `/web/sales/production-orders/${encodeURIComponent(name)}`,
	"SD YRP Cutting Order": (name) => `/web/cutting/orders/${encodeURIComponent(name)}`,
	"SD YRP Cutting Bulk Lay Sheets": (name) => `/web/cutting/bulk-lay-sheets/${encodeURIComponent(name)}`,
	"SD YRP Cutting Laysheet Planner": (name) => `/web/cutting/lay-sheet-planner/${encodeURIComponent(name)}`,
	"YRP Debit": (name) => `/web/accounts/debits/${encodeURIComponent(name)}`,
	"SD YRP Lot": (name) => `/web/purchase/lots/${encodeURIComponent(name)}`,
	"YRP Work Order": (name) => `/web/fabric-store/work-orders/${encodeURIComponent(name)}`,
	"Purchase Order": (name) => `/web/fabric-store/purchase-orders/${encodeURIComponent(name)}`,
	"YRP Delivery Challan": (name) => `/web/fabric-store/delivery-challans/${encodeURIComponent(name)}`,
	"YRP Goods Received Note": (name) => `/web/fabric-store/goods-received-notes/${encodeURIComponent(name)}`,
	"SD YRP Cutting Plan": (name) => `/web/cutting/plans/${encodeURIComponent(name)}`,
	"SD YRP Finishing Plan": (name) => `/web/finishing/plans/${encodeURIComponent(name)}`,
	"SD YRP Finishing Plan Dispatch": (name) => `/web/finishing/dispatches/${encodeURIComponent(name)}`,
	"SD YRP Product": (name) => `/web/pd/products/${encodeURIComponent(name)}`,
	"SD YRP Product Release": (name) => `/web/pd/product-releases/${encodeURIComponent(name)}`,
	"SD YRP Lotwise Item Profit": (name) => `/web/pd/lotwise-item-profits/${encodeURIComponent(name)}`,
	"YRP Purchase Invoice": (name) => `/web/accounts/purchase-invoices/${encodeURIComponent(name)}`,
	"YRP Bill Tracking": (name) => `/web/hr/bill-tracking/${encodeURIComponent(name)}`,
	"YRP Item Price": (name) => `/web/purchase/item-prices/${encodeURIComponent(name)}`,
	"YRP Item Production Detail": (name) => `/web/merch/item-production-details/${encodeURIComponent(name)}`,
	"YRP Process Cost": (name) => `/web/merch/process-costs/${encodeURIComponent(name)}`,
}

export const DEPARTMENT_RECORD_ROUTES = {
	"/planning": {
		"SD YRP Lot": (name) => `/web/planning/lots/${encodeURIComponent(name)}`,
		"YRP Work Order": (name) => `/web/planning/work-orders/${encodeURIComponent(name)}`,
		"YRP Production Order": (name) => `/web/planning/production-orders/${encodeURIComponent(name)}`,
		"SD YRP Cutting Plan": (name) => `/web/planning/cutting-plans/${encodeURIComponent(name)}`,
		"SD YRP Finishing Plan": (name) => `/web/planning/finishing-plans/${encodeURIComponent(name)}`,
	},
	"/merch": {
		"SD YRP Lot": (name) => `/web/merch/lots/${encodeURIComponent(name)}`,
		"YRP Work Order": (name) => `/web/merch/work-orders/${encodeURIComponent(name)}`,
		"YRP Production Order": (name) => `/web/merch/production-orders/${encodeURIComponent(name)}`,
		"YRP Process Cost": (name) => `/web/merch/process-costs/${encodeURIComponent(name)}`,
		"YRP Bill Tracking": (name) => `/web/merch/bill-tracking/${encodeURIComponent(name)}`,
		"YRP Purchase Invoice": (name) => `/web/merch/purchase-invoices/${encodeURIComponent(name)}`,
		"YRP Item Production Detail": (name) => `/web/merch/item-production-details/${encodeURIComponent(name)}`,
	},
}

function documentPage(doctype, currentPath = globalThis.location?.pathname) {
	const department = Object.keys(DEPARTMENT_RECORD_ROUTES).find(
		(path) => currentPath === `/web${path}` || currentPath?.startsWith(`/web${path}/`),
	)
	return DEPARTMENT_RECORD_ROUTES[department]?.[doctype] || recordRoutes[doctype]
}

export function hasWebDocumentPage(doctype, currentPath) {
	return Boolean(documentPage(doctype, currentPath))
}

export function webDocumentPath(doctype, name, currentPath = globalThis.location?.pathname) {
	if (!doctype || !name) return "/web/document-unavailable"
	const page = documentPage(doctype, currentPath)
	if (page) return page(String(name))
	const query = new URLSearchParams({ doctype: String(doctype), name: String(name) })
	return `/web/document-unavailable?${query.toString()}`
}

export function webDocumentRoute(doctype, name, currentPath) {
	return webDocumentPath(doctype, name, currentPath).replace(/^\/web(?=\/|$)/, "") || "/"
}
