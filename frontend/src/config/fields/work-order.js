/**
 * Work Order — per-DocType field config consumed by DocDetail.vue.
 *
 * Three concerns:
 *   • `detail`  — curated Details-tab list shown in VIEW mode (mirrors the
 *                 essdee /web plan; tighter than meta order).
 *   • `formOrder` — exact field order for EDIT / CREATE mode. Mirrors the Desk
 *                 form so naming_series is the first user-facing input.
 *   • `hideFormFields` — fields the user explicitly does not want surfaced in
 *                 the form (e.g. `includes_packing` — packing is computed from
 *                 the Item context on this floor).
 *   • `linkSearchHandlers` — per-Link-field custom search factories. Each
 *                 receives the reactive form object and returns either an async
 *                 `(query) => Array<{ name }>` (when a filter applies) or null
 *                 (fall through to the default name-like search). Used to
 *                 restrict the Address autocomplete to addresses belonging to
 *                 the selected party, the same way the Desk does.
 */
import { searchAddressForParty } from "@/api/client"

// Curated VIEW Details grouping. Work Order's own DocType layout is a flat
// 26-field top section + several UNNAMED sections, so meta Section-Break
// grouping would render one giant card + repeated "More" cards. These named
// groups give it the same tidy multi-card Details tab as Delivery Challan.
// Fields not present / hidden / read-only-empty are dropped per-group by
// DocDetail; a group whose fields all drop is not rendered. JSON blobs and the
// *_details / *_name / amended_from noise are filtered globally, so they are
// intentionally omitted here.
const detailGroups = [
	{
		label: "Identity",
		fields: [
			"naming_series", "status", "is_rework", "rework_type",
			"process_name", "lot", "item", "production_detail", "parent_wo",
		],
	},
	{
		label: "Supplier & Delivery",
		fields: [
			"supplier", "supplier_type", "supplier_address",
			"delivery_location", "delivery_address", "terms_and_condition",
		],
	},
	{
		label: "Schedule",
		fields: [
			"wo_date", "planned_start_date", "planned_end_date", "planned_quantity", "expected_delivery_date",
			"start_date", "end_date", "first_dc_date", "last_dc_date", "first_grn_date", "last_grn_date",
		],
	},
	{
		label: "Quantities",
		fields: [
			"total_quantity",
			"total_no_of_pieces_delivered", "total_no_of_pieces_received", "wo_colours",
		],
	},
	{
		label: "Status & Closure",
		fields: [
			"open_status", "is_delivered", "is_internal_unit", "includes_packing", "is_manual_entry",
			"sd_close_reason", "close_other_reason", "close_remarks", "closed_by",
			"approved_by", "rejection_reason",
		],
	},
	{
		label: "Stock & Costing",
		fields: ["process_cost", "reduce_stock_entry", "update_stock_entry"],
	},
	{
		label: "Notes",
		fields: ["comments"],
	},
]

// Form-mode field order — every editable field listed in the order the Desk
// would render it. System-managed / depends_on-gated fields stay in the list
// so they appear in the right place if they ever become visible (e.g.
// supplier_type/rework_type when is_rework is on). Hidden + read-only-empty
// fields are filtered out downstream by DocDetail.
const formOrder = [
	"naming_series",
	"edit_wo_date",
	"wo_date",
	"process_name",
	"lot",
	"item",
	"production_detail",
	"supplier",
	"supplier_name",
	"parent_wo",
	"terms_and_condition",
	"delivery_location",
	"delivery_location_name",
	"planned_start_date",
	"planned_end_date",
	"planned_quantity",
	"expected_delivery_date",
	"supplier_type",
	"rework_type",
	"supplier_address",
	"supplier_address_details",
	"delivery_address",
	"delivery_address_details",
	"comments",
]

// Hide unconditionally in EDIT/CREATE:
// - includes_packing: user opted out (2026-05-29).
// - open_status / is_delivered / status: system-managed read-only fields
//   that have non-empty defaults ("Open" / 0 / "0"). The shared visibility
//   rule "read-only + empty → hide" wouldn't drop them (Check is never
//   "empty", and the strings are non-empty), so they'd leak into the New
//   WO form as disabled controls — distracting and against the U4 audit
//   intent. Listed here explicitly.
// - comments: dropped from the regular form-field grid so it can be re-rendered
//   as the VERY LAST element of the WO form — below the
//   deliverables/receivables pivots (DocDetail renders a dedicated WO comments
//   block after all child tables). Mirrors the Desk's bottom-of-form placement.
const hideFormFields = [
	"includes_packing",
	"open_status",
	"is_delivered",
	"status",
	"comments",
]

// Empty-party handler used by the address fields below: returns no suggestions
// (instead of falling through to the default name-like search, which would
// list ALL addresses on the site and let the user assign a wrong-party
// address). Mirrors the Desk's "select party first" behaviour.
const emptyHandler = async () => []

const linkSearchHandlers = {
	supplier_address: (form) =>
		form.supplier
			? (q) => searchAddressForParty("YRP Supplier", form.supplier, q)
			: emptyHandler,
	delivery_address: (form) =>
		form.delivery_location
			? (q) => searchAddressForParty("YRP Supplier", form.delivery_location, q)
			: emptyHandler,
}

// Use the DocType's standard Supplier terminology consistently in every shell.
const labels = {
	supplier: "YRP Supplier",
	supplier_name: "Supplier Name",
	supplier_address: "Supplier Address",
	process_name: "YRP Process",
	production_detail: "YRP Item Production Detail",
}

const help = {
	process_name: "Select the Process first; the Lot and valid Item/IPD choices follow from it.",
	lot: "Available after Process is selected.",
	item: "Auto-filled when one valid Item exists; otherwise limited to this Process and Lot.",
	production_detail: "Read-only; resolved from the selected Process, Lot, and Item.",
}

export default {
	detailGroups,
	formOrder,
	hideFormFields,
	linkSearchHandlers,
	labels,
	help,
}
