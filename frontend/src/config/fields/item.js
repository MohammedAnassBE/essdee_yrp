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
const hideFormFields = [
	"weight_per_unit",
	"weight_uom",
]

const readOnlyChildFields = {
	"Item Item Attribute": ["mapping"],
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

export default {
	hideFormFields,
	readOnlyChildFields,
	boolLabels,
	labels,
}
