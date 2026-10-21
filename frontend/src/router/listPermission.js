import { canReadDoctype } from "../utils/linkTarget.js"

export const NO_PERMISSION_PATH = "/no-permission"

/** DocType listed by each `/<department>/<segment>` list page; boot.user.can_read (server has_permission) decides access. */
const SEGMENT_DOCTYPES = {
	"work-orders": "YRP Work Order",
	"purchase-orders": "Purchase Order",
	"delivery-challans": "YRP Delivery Challan",
	"goods-received-notes": "YRP Goods Received Note",
	movements: "SD YRP Cut Panel Movement",
	"cut-bundle-edits": "SD YRP Cut Bundle Edit",
	"box-sticker-prints": "SD YRP Box Sticker Print",
	"excel-sticker-prints": "YRP Excel Sticker Print",
	"cutting-plans": "SD YRP Cutting Plan",
	"sewing-plans": "SD YRP Sewing Plan",
	"finishing-plans": "SD YRP Finishing Plan",
	"bulk-lay-sheets": "SD YRP Cutting Bulk Lay Sheets",
	"lay-sheet-planner": "SD YRP Cutting Laysheet Planner",
	lots: "SD YRP Lot",
	"item-production-details": "YRP Item Production Detail",
	"production-orders": "YRP Production Order",
	"process-costs": "YRP Process Cost",
	"bill-tracking": "YRP Bill Tracking",
	"purchase-invoices": "YRP Purchase Invoice",
	items: "Item",
	"item-prices": "YRP Item Price",
	products: "SD YRP Product",
	"product-releases": "SD YRP Product Release",
	"lotwise-item-profits": "SD YRP Lotwise Item Profit",
	debits: "YRP Debit",
	inspections: "SD YRP Essdee Quality Inspection",
}

const PATH_DOCTYPES = {
	"cutting/plans": "SD YRP Cutting Plan",
	"cutting/orders": "SD YRP Cutting Order",
	"sewing/plans": "SD YRP Sewing Plan",
	"finishing/plans": "SD YRP Finishing Plan",
}

/** DocType a list page at `target` (path or route location) shows, or null when it is not a DocType list. */
export function getListDoctype(target) {
	const path = typeof target === "string" ? target : target?.path
	const segments = String(path || "").toLowerCase().split(/[?#]/)[0].split("/").filter(Boolean)
	if (segments.length !== 2) return null
	return PATH_DOCTYPES[segments.join("/")] || SEGMENT_DOCTYPES[segments[1]] || null
}

export function canOpenList(target, boot) {
	const doctype = getListDoctype(target)
	return !doctype || canReadDoctype(doctype, boot)
}

/** Guard result: a list page for a DocType the user cannot read shows the permission page instead. */
export function getPermissionRedirect(to, boot) {
	const doctype = getListDoctype(to)
	if (!doctype || canReadDoctype(doctype, boot)) return undefined
	return { path: NO_PERMISSION_PATH, query: { doctype, from: to.fullPath || to.path }, replace: true }
}
