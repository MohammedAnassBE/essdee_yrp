/**
 * Lot — per-DocType field config consumed by DocDetail.vue.
 *
 * The Lot's real data-entry surfaces are the two custom editors DocDetail
 * mounts for it (LotOrderEditor ↔ item_details, LotOrderDetailGrid ↔
 * order_item_details) — the Desk parallels are the LotOrder / CutPlanItems
 * Vue islands. The HTML mount-point fields those islands use on Desk are
 * meaningless here and are hidden from the generic form.
 *
 * `linkSearchHandlers` mirror lot.js's set_query rules: production_detail is
 * filtered to the chosen item's IPDs; production_order to submitted POs of the
 * item.
 */
import { searchLink } from "@/api/client"

const hideFormFields = [
	"items_html",
	"lot_item_order_detail_html",
	"ocr_detail_html",
	"alternative_html",
	"size_set_colour_colour",
	"size_set_colour",
	"calculate_bom",
]

const linkSearchHandlers = {
	production_detail: (form) =>
		form.item ? (q) => searchLink("Item Production Detail", q, { item: form.item }) : null,
	production_order: (form) =>
		form.item
			? (q) => searchLink("Production Order", q, { item: form.item, docstatus: 1 })
			: (q) => searchLink("Production Order", q, { docstatus: 1 }),
}

const labels = {
	production_detail: "Item Production Detail",
}

export default {
	hideFormFields,
	linkSearchHandlers,
	labels,
}
