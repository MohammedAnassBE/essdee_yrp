/**
 * Essdee YRP — static DocType registry.
 *
 * The /web UI manages EXACTLY these 8 DocTypes (user scope, 2026-07-03):
 * Lot, Work Order, Delivery Challan, Goods Received Note, Stock Entry,
 * Item, Item Production Detail, Terms and Condition. Nothing else appears
 * in the sidebar / routes / command palette.
 *
 * Used for: sidebar rendering, route → DocType resolution, submittable flags
 * (drives the All/Draft/Submitted/Cancelled tab strip) and per-doctype tab
 * behaviour. No DB fetch — instant lookup.
 *
 * Route convention (slugify): DocType label lowercased, non-alphanumerics →
 * "-". e.g. "Goods Received Note" → "goods-received-note".
 *
 * `roles`: coarse grouping hint only — the sidebar hard-gates every item on
 * live `canRead(doctype)` from frappe.boot, so real visibility is
 * permission-driven.
 */

// Submittable transaction DocTypes — get the docstatus tab strip + the plain
// Submit/Cancel buttons on the detail page. Verified against is_submittable
// on essdee_yrp.site (2026-07-03): Lot, Item, Item Production Detail and
// Terms and Condition are NOT submittable.
const SUBMITTABLE = new Set([
	"Work Order",
	"Delivery Challan",
	"Goods Received Note",
	"Stock Entry",
])

// No workflow-managed doctypes among the essdee /web 8 (the site's two active
// Workflows — Process Cost, Item Price — are outside this UI's scope).
const WORKFLOW = {}

// Workflow-state → PrimeVue Tag severity. Kept for the shared Tag helpers even
// though WORKFLOW is empty (list/detail import this).
export const WORKFLOW_SEVERITY = {
	Approved: "success",
	Rejected: "danger",
	Expired: "danger",
	"Approval Pending": "warn",
	Draft: "warn",
}

function slugify(s) {
	return s
		.toLowerCase()
		.replace(/&/g, "")
		.replace(/[^a-z0-9]+/g, "-")
		.replace(/(^-|-$)/g, "")
}

// Raw group definitions (order = sidebar order). Icons are primeicons names.
const GROUPS = [
	{
		group: "Production",
		roles: "*",
		items: [
			// Lot: not submittable, has a status Select (Open/Closed) → status
			// tabs + All per the finalized tab rules.
			{ doctype: "Lot", icon: "pi pi-inbox", tabMode: "status", listFields: [
				{ field: "item", label: "Item" },
				{ field: "production_detail", label: "IPD" },
				{ field: "expected_delivery_date", label: "Delivery", type: "Date" },
			] },
			// Work Order is submittable but its lifecycle is driven by its
			// many-valued `status` Select — keep the explicit status override
			// (Submit/Cancel still work via the detail-page buttons).
			{ doctype: "Work Order", icon: "pi pi-bars", dateTabs: "wo_date", tabMode: "status", listFields: [
				{ field: "item", label: "Item" },
				{ field: "supplier", label: "Job-worker" },
				{ field: "process_name", label: "Process" },
				{ field: "wo_date", label: "WO Date", type: "Date" },
			] },
			{ doctype: "Delivery Challan", icon: "pi pi-send", dateTabs: "posting_date", listFields: [
				{ field: "work_order", label: "Work Order" },
				{ field: "supplier", label: "Job-worker" },
				{ field: "posting_date", label: "Posting", type: "Date" },
			] },
			{ doctype: "Goods Received Note", icon: "pi pi-plus-circle", dateTabs: "posting_date", listFields: [
				{ field: "supplier", label: "Supplier" },
				{ field: "delivery_challan", label: "Against DC" },
				{ field: "posting_date", label: "Posting", type: "Date" },
			] },
		],
	},
	{
		group: "Stock",
		roles: "*",
		items: [
			{ doctype: "Stock Entry", icon: "pi pi-sync", dateTabs: "posting_date" },
		],
	},
	{
		group: "Item Masters",
		roles: "*",
		items: [
			{ doctype: "Item", icon: "pi pi-box", listFields: [
				{ field: "name1", label: "Item Name" },
				{ field: "item_group", label: "Item Group" },
				{ field: "default_unit_of_measure", label: "UOM" },
			] },
			{ doctype: "Item Production Detail", icon: "pi pi-table" },
		],
	},
	{
		group: "Setup",
		roles: "*",
		items: [
			{ doctype: "Terms and Condition", icon: "pi pi-book" },
		],
	},
]

// Flatten into a registry with derived route/label/isSubmittable.
const DOCTYPES = []
for (const g of GROUPS) {
	for (const it of g.items) {
		DOCTYPES.push({
			doctype: it.doctype,
			route: slugify(it.doctype),
			label: it.doctype,
			icon: it.icon,
			group: g.group,
			roles: g.roles,
			isSubmittable: SUBMITTABLE.has(it.doctype),
			isWorkflow: it.doctype in WORKFLOW,
			workflowStates: WORKFLOW[it.doctype] || null,
			// OPT-IN tab-mode override. When set ('status' | 'docstatus' | 'workflow'),
			// DynamicListPage.loadMetaAndColumns() honors it BEFORE the automatic
			// workflow > submittable > status > all priority.
			tabMode: it.tabMode || null,
			dateTabs: it.dateTabs || null,
			listFields: it.listFields || null,
			hasAddressContact: it.hasAddressContact || false,
			note: it.note || null,
		})
	}
}

// Default columns for any DocType without an explicit listFields config.
export const GENERIC_FIELDS = [
	{ field: "modified", label: "Last Updated", type: "Datetime" },
]

export function getRegistryByRoute(slug) {
	return DOCTYPES.find((d) => d.route === slug) || null
}

export function getRegistryByDoctype(name) {
	return DOCTYPES.find((d) => d.doctype === name) || null
}

/**
 * Sidebar groups in declared order. The `filterFn(doctype)` lets the sidebar
 * drop items the user can't read (live perms). Home is injected separately.
 */
export function getSidebarGroups(filterFn = () => true) {
	return GROUPS.map((g) => ({
		group: g.group,
		items: DOCTYPES.filter(
			(d) => d.group === g.group && filterFn(d.doctype)
		),
	})).filter((g) => g.items.length > 0)
}

export { DOCTYPES, SUBMITTABLE, WORKFLOW }
