/**
 * Per-DocType field configs for the detail page.
 *
 * Each module under this folder default-exports an object:
 *   {
 *     detail?:             Array<{ fieldname, label, type? }>  // VIEW Details-tab grid
 *     formOrder?:          Array<string>                       // EDIT/CREATE field order
 *     hideFormFields?:     Array<string>                       // never render in EDIT/CREATE
 *     linkSearchHandlers?: Record<string, (form) => fn|null>   // per-Link custom search
 *     labels?:             Record<string, string>              // relabel a field (overrides meta)
 *     help?:               Record<string, string>              // inline field help (overrides meta description)
 *     boolLabels?:         Record<string, {on, off}>           // Check field display words (Q20 positive display)
 *     hero?:               Array<string>                       // load-bearing fields to emphasise (Q2/Q4)
 *   }
 *
 * Missing parts fall back to meta-driven defaults in DocDetail.vue. So a
 * DocType with no config still renders a usable detail + form page.
 *
 * Route convention matches config/doctypes.js slugify (label → kebab-case).
 */

import workOrder from "./work-order.js"
import deliveryChallan from "./delivery-challan.js"
import goodsReceivedNote from "./goods-received-note.js"
import item from "./item.js"
import lot from "./lot.js"
import itemProductionDetail from "./item-production-detail.js"

const FIELD_CONFIGS = {
	"Work Order": workOrder,
	"Delivery Challan": deliveryChallan,
	"Goods Received Note": goodsReceivedNote,
	"Item": item,
	"Lot": lot,
	"Item Production Detail": itemProductionDetail,
}

/**
 * VIEW Details-tab curated field list, or null to fall back to meta.
 */
export function getDetailFieldConfig(doctype) {
	return FIELD_CONFIGS[doctype]?.detail || null
}

/**
 * Curated VIEW Details grouping: Array<{ label, key?, fields: Array<string |
 * {fieldname, label?, type?}> }>, or null to fall back to meta Section-Break
 * grouping. Use this for DocTypes whose own section structure is flat/unnamed
 * (e.g. Work Order's 26-field top section) so the Details tab still renders as
 * tidy, meaningfully-titled cards instead of one giant card. Takes precedence
 * over `detail` (single card) and meta grouping in DocDetail.detailSections.
 */
export function getDetailGroups(doctype) {
	return FIELD_CONFIGS[doctype]?.detailGroups || null
}

/**
 * EDIT/CREATE field-order array (config-listed fields first, rest appended
 * by DocDetail in meta order). null means "use meta order entirely".
 */
export function getFormFieldOrder(doctype) {
	return FIELD_CONFIGS[doctype]?.formOrder || null
}

/**
 * Set of fieldnames to hide from EDIT/CREATE for the given DocType.
 * Returns an empty Set when no overrides exist (so callers can `.has()` safely).
 */
export function getHiddenFormFields(doctype) {
	return new Set(FIELD_CONFIGS[doctype]?.hideFormFields || [])
}

/**
 * Set of fieldnames to hide from the VIEW Details tab for the given DocType.
 * For fields that are rendered elsewhere as dedicated UI (e.g. the DC/GRN
 * transfer indicators shown as badges at the top of the Details tab) so they
 * must not ALSO appear as ordinary detail-card fields. Empty Set when none.
 */
export function getHiddenViewFields(doctype) {
	return new Set(FIELD_CONFIGS[doctype]?.hideViewFields || [])
}

/**
 * Custom Link search handler for one field on `doctype`. The factory closes
 * over the live `form` so calling code re-evaluates on each render — when the
 * controlling field changes (e.g. supplier), the returned handler refreshes.
 *
 * Returns null when no custom handler applies — LinkField falls back to the
 * default name-like search.
 */
export function getLinkSearchHandler(doctype, fieldname, form) {
	const factory = FIELD_CONFIGS[doctype]?.linkSearchHandlers?.[fieldname]
	if (typeof factory !== "function") return null
	return factory(form)
}

/**
 * Set of child-table fieldnames that must render as DISPLAY-ONLY in the
 * edit grid for the given parent doctype + child doctype. Empty Set when
 * no override exists. Currently used to make `Item Item Attribute.mapping`
 * non-editable: base yrp auto-creates the mapping on save, so the user
 * picking an existing one would silently share state across items.
 */
export function getReadOnlyChildFields(doctype, childDoctype) {
	const list = FIELD_CONFIGS[doctype]?.readOnlyChildFields?.[childDoctype] || []
	return new Set(list)
}

// ── UX override layer (Q13/Q18/Q20/Q2) ──────────────────────────────────────
// These let the SPA relabel, help-annotate, humanise booleans, and emphasise
// fields WITHOUT touching the base-yrp DocType JSON (the plan's standing rule:
// "override yrp labels in the SPA field-config layer, not the DocType JSON").

// Site-wide defaults applied when a doctype config doesn't override the field.
// Negatively-named flags read as a double-negative ("Disabled: No"); show the
// effective state instead. Per-doctype `boolLabels` win over these.
const GLOBAL_BOOL_LABELS = {
	disabled: { on: "Disabled", off: "Active" },
	is_disabled: { on: "Disabled", off: "Active" },
}

/**
 * UX label override for one field, or null to fall back to meta label / humanize.
 * Used to unify the vendor party to a single term ("Job-worker") across WO/DC/GRN
 * and to plain-language a few engine-speak field names.
 */
export function getFieldLabel(doctype, fieldname) {
	return FIELD_CONFIGS[doctype]?.labels?.[fieldname] || null
}

/**
 * Inline help text for one field, or null. Falls back (in DocDetail) to the
 * meta `description` when no override is set.
 */
export function getFieldHelp(doctype, fieldname) {
	return FIELD_CONFIGS[doctype]?.help?.[fieldname] || null
}

/**
 * `{ on, off }` display words for a Check field, or null. Per-doctype config wins
 * over the GLOBAL_BOOL_LABELS site defaults.
 */
export function getBoolLabels(doctype, fieldname) {
	return (
		FIELD_CONFIGS[doctype]?.boolLabels?.[fieldname] ||
		GLOBAL_BOOL_LABELS[fieldname] ||
		null
	)
}

/**
 * Set of load-bearing fieldnames to emphasise in the detail cards. Empty Set
 * when none configured (safe to `.has()`).
 */
export function getHeroFields(doctype) {
	return new Set(FIELD_CONFIGS[doctype]?.hero || [])
}
