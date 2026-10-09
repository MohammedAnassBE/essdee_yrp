const recordRoutes = {
	"YRP Work Order": (name) => `/web/fabric-store/work-orders/${encodeURIComponent(name)}`,
	"Purchase Order": (name) => `/web/fabric-store/purchase-orders/${encodeURIComponent(name)}`,
	"YRP Delivery Challan": (name) => `/web/fabric-store/delivery-challans/${encodeURIComponent(name)}`,
	"YRP Goods Received Note": (name) => `/web/fabric-store/goods-received-notes/${encodeURIComponent(name)}`,
	"SD YRP Cutting Plan": (name) => `/web/cutting/plans/${encodeURIComponent(name)}`,
	"SD YRP Finishing Plan": (name) => `/web/finishing/plans/${encodeURIComponent(name)}`,
	"SD YRP Finishing Plan Dispatch": (name) => `/web/finishing/dispatches/${encodeURIComponent(name)}`,
}

export function webDocumentPath(doctype, name) {
	if (!doctype || !name) return "/web/document-unavailable"
	if (recordRoutes[doctype]) return recordRoutes[doctype](String(name))
	const query = new URLSearchParams({ doctype: String(doctype), name: String(name) })
	return `/web/document-unavailable?${query.toString()}`
}
