/**
 * Item — per-DocType field config consumed by DocDetail.vue.
 *
 * `hideFormFields`: drop fields the user explicitly doesn't want surfaced
 * in the EDIT/CREATE form. weight_per_unit / weight_uom are tracked
 * elsewhere on this site and add noise here.
 *
 * `readOnlyChildFields`: per-child-doctype field name set. Cells in those
 * columns render as display-only spans in the edit grid — used to prevent
 * the user from picking an existing shared mapping for the Attributes
 * table, since base yrp's `Item._ensure_attribute_mappings_exist`
 * auto-creates one on save.
 *
 * `boolLabels`: humanise essdee's `is_cloth_item` Check so it reads as a
 * clear yes/no on the form rather than the raw "Is Cloth Item: No"
 * double-take. The field is meta-driven, so it renders automatically in
 * EDIT/CREATE as a toggle; cloth items drive the fabric (knitting/dyeing/
 * compacting) IPD tabs and the Lot fabric-details rows.
 */
import { searchLink } from "@/api/client"

const hideFormFields = [
	"weight_per_unit",
	"weight_uom",
]

const readOnlyChildFields = {
	"YRP Item Item Attribute": ["mapping"],
}

const boolLabels = {
	is_cloth_item: { on: "Cloth item", off: "Not a cloth item" },
}

// `name1`'s base-yrp meta label is literally "Name", so the Item list showed
// two columns both headed "Name" (the doc code + this). Relabel it "Item Name"
// so the list header is unambiguous (getFieldLabel applies to list headers).
const labels = {
	name1: "Item Name",
}

// Keep the /web pickers inside the same legal subset as Desk. The server also
// validates the default UOM, but filtering here avoids presenting values that
// can never be saved; Item Group has no equivalent controller guard, so the
// leaf-only filter is especially important.
const linkSearchHandlers = {
	item_group: () => (q) => searchLink("YRP Item Group", q, { is_group: 0 }),
	default_unit_of_measure: () => (q) => searchLink("YRP UOM", q, { secondary_only: 0 }),
}

export default {
	hideFormFields,
	readOnlyChildFields,
	boolLabels,
	labels,
	linkSearchHandlers,
}
