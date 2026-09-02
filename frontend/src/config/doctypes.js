/**
 * SD YRP — static DocType registry.
 *
 * The /web UI manages these production DocTypes (user scope, 2026-07-03;
 * Work Order Correction added 2026-07-09; Process Cost and Lot Transfer added
 * 2026-07-29): Lot, Work Order, Work Order Correction, Delivery Challan,
 * Goods Received Note, Process Cost, Stock Entry, Lot Transfer, Item, Item
 * Production Detail, and Terms and Condition.
 *
 * Used for: sidebar rendering, route → DocType resolution, submittable flags
 * (drives the All/Draft/Submitted/Cancelled tab strip) and per-doctype tab
 * behaviour. No DB fetch — instant lookup.
 *
 * Route convention (slugify): DocType label lowercased, non-alphanumerics →
 * "-". e.g. "YRP Goods Received Note" → "goods-received-note".
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
	"YRP Work Order",
	"YRP Work Order Correction",
	"YRP Delivery Challan",
	"YRP Goods Received Note",
	"YRP Process Cost",
	"SD YRP Lot Transfer",
	"YRP Stock Entry",
])

const WORKFLOW = {
	"YRP Process Cost": ["Draft", "Approval Pending", "Approved", "Rejected", "Expired"],
}

// Workflow-state → PrimeVue Tag severity for the shared list/detail helpers.
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
			// noCreate: synced via spine_consumer_config — no /web create.
			{ doctype: "SD YRP Lot", icon: "pi pi-inbox", tabMode: "status", noCreate: true, listFields: [
				{ field: "item", label: "Item" },
				{ field: "production_detail", label: "IPD" },
				{ field: "expected_delivery_date", label: "Delivery", type: "Date" },
			] },
			// Work Order is submittable but its lifecycle is driven by its
			// many-valued `status` Select — keep the explicit status override
			// (Submit/Cancel still work via the detail-page buttons).
			{ doctype: "YRP Work Order", icon: "pi pi-bars", dateTabs: "wo_date", tabMode: "status", listFields: [
				{ field: "item", label: "Item" },
				{ field: "supplier", label: "Job-worker" },
				{ field: "process_name", label: "Process" },
				{ field: "wo_date", label: "WO Date", type: "Date" },
			] },
			// Work Order Correction: extra deliverables/receivables against a
			// submitted WO (user, 2026-07-09: must be in the /web left panel).
			// Submittable with a many-valued status Select — status tabs like WO.
			{ doctype: "YRP Work Order Correction", icon: "pi pi-pencil", dateTabs: "correction_date", tabMode: "status", listFields: [
				{ field: "work_order", label: "Work Order" },
				{ field: "supplier", label: "Job-worker" },
				{ field: "process_name", label: "Process" },
				{ field: "correction_date", label: "Correction Date", type: "Date" },
			] },
			{ doctype: "YRP Delivery Challan", icon: "pi pi-send", dateTabs: "posting_date", listFields: [
				{ field: "work_order", label: "Work Order" },
				{ field: "supplier", label: "Job-worker" },
				{ field: "posting_date", label: "Posting", type: "Date" },
			] },
			{ doctype: "YRP Goods Received Note", icon: "pi pi-plus-circle", dateTabs: "posting_date", listFields: [
				{ field: "supplier", label: "Supplier" },
				{ field: "delivery_challan", label: "Against DC" },
				{ field: "posting_date", label: "Posting", type: "Date" },
			] },
			{ doctype: "YRP Process Cost", icon: "pi pi-indian-rupee", dateTabs: "from_date", tabMode: "workflow", listFields: [
				{ field: "process_name", label: "Process" },
				{ field: "supplier", label: "Supplier" },
				{ field: "item", label: "Item" },
				{ field: "from_date", label: "From Date", type: "Date" },
				{ field: "to_date", label: "To Date", type: "Date" },
			] },
		],
	},
	{
		group: "Stock",
		roles: "*",
		items: [
			{ doctype: "YRP Stock Entry", icon: "pi pi-sync", dateTabs: "posting_date" },
			{ doctype: "SD YRP Lot Transfer", icon: "pi pi-arrow-right-arrow-left", dateTabs: "posting_date", listFields: [
				{ field: "posting_date", label: "Posting Date", type: "Date" },
				{ field: "comments", label: "Comments" },
			] },
		],
	},
	{
		group: "Item Masters",
		roles: "*",
		items: [
			// noCreate: synced via spine_consumer_config — no /web create.
			{ doctype: "YRP Item", icon: "pi pi-box", noCreate: true, listFields: [
				{ field: "name1", label: "Item Name" },
				{ field: "item_group", label: "Item Group" },
				{ field: "default_unit_of_measure", label: "UOM" },
			] },
			{ doctype: "YRP Item Production Detail", icon: "pi pi-table" },
		],
	},
	{
		group: "Setup",
		roles: "*",
		items: [
			// noCreate: synced via spine_consumer_config — no /web create.
			{ doctype: "YRP Terms and Condition", icon: "pi pi-book", noCreate: true },
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
			// Catalog-level create block: these doctypes are populated by an
			// external sync (spine_consumer_config) and must NEVER be created in
			// /web. Applies to ALL layouts and ALL users — see noWebCreate() below,
			// consumed by every create gate (list New, home CTA, palette, route).
			noCreate: it.noCreate || false,
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

// Catalog-level create block. True for doctypes flagged `noCreate` (Lot, Item,
// Terms and Condition) — externally synced via spine_consumer_config, so /web
// must never offer a create affordance for them. Every create gate consults
// this (permission funnels canCreate/gateCreate + the /:doctype/new route),
// so the rule holds for ALL layouts and ALL users, admin included.
export function noWebCreate(name) {
	return getRegistryByDoctype(name)?.noCreate === true
}

export { DOCTYPES, SUBMITTABLE, WORKFLOW }
