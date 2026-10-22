/** /web departments. `sections` maps each launcher workspace key to the route segment(s) under `path` it owns; `combines` adds the sections of other departments. */
export const departments = [
	{
		key: "cutting",
		label: "Cutting",
		shortLabel: "CT",
		path: "/cutting",
		sections: { "cutting-plans": "plans", "cutting-orders": "orders", "bulk-lay-sheets": "bulk-lay-sheets", "lay-sheet-planner": "lay-sheet-planner", reports: "reports" },
		component: () => import("./Cutting.vue"),
	},
	{
		key: "fabric-store",
		label: "Fabric Store",
		shortLabel: "FS",
		path: "/fabric-store",
		sections: { work_orders: ["work-orders", "delivery-challans", "goods-received-notes"], purchase_orders: ["purchase-orders", "goods-received-notes"], stock_transfers: "stock-transfers", reports: "reports" },
		component: () => import("./FabricStore.vue"),
	},
	{
		key: "cut-panel-store",
		label: "Cut Panel Store",
		shortLabel: "CP",
		path: "/cut-panel-store",
		sections: { delivery_challans: "delivery-challans", goods_received_notes: "goods-received-notes", movements: "movements", work_orders: "work-orders", cut_bundle_edits: "cut-bundle-edits", box_stickers: "box-sticker-prints", excel_stickers: "excel-sticker-prints", reports: "reports" },
		component: () => import("./CutPanelStore.vue"),
	},
	{
		key: "accessory-store",
		label: "Accessory Store",
		shortLabel: "AS",
		path: "/accessory-store",
		sections: { work_orders: ["work-orders", "delivery-challans", "goods-received-notes"], purchase_orders: ["purchase-orders", "goods-received-notes"], stock_transfers: "stock-transfers", reports: "reports" },
		component: () => import("./AccessoryStore.vue"),
	},
	{
		key: "sewing",
		label: "Sewing",
		shortLabel: "SW",
		path: "/sewing",
		sections: { plans: "plans", work_orders: ["work-orders", "delivery-challans", "goods-received-notes"], reports: "reports", attendance: "attendance" },
		component: () => import("./Sewing.vue"),
	},
	{
		key: "finishing",
		label: "Finishing",
		shortLabel: "FN",
		path: "/finishing",
		sections: { plans: "plans", reports: "reports", rework_details: "rework-details", rework_groups: "rework-groups", dispatches: "dispatches" },
		component: () => import("./Finishing.vue"),
	},
	{
		key: "quality",
		label: "Quality",
		shortLabel: "QA",
		path: "/quality",
		sections: { inspections: "inspections", work_orders: "work-orders", reports: "reports" },
		component: () => import("./Quality.vue"),
	},
	{
		key: "merch",
		label: "Merch",
		shortLabel: "MR",
		path: "/merch",
		sections: { lots: "lots", item_production_details: "item-production-details", production_orders: "production-orders", work_orders: "work-orders", process_costs: "process-costs", bill_tracking: "bill-tracking", purchase_invoices: "purchase-invoices", reports: "reports" },
		component: () => import("./Merch.vue"),
	},
	{
		key: "purchase",
		label: "Purchase",
		shortLabel: "PU",
		path: "/purchase",
		sections: { lots: "lots", items: "items", item_prices: "item-prices", purchase_orders: "purchase-orders", stock_transfers: "stock-transfers", box_stickers: "box-sticker-prints", reports: "reports" },
		component: () => import("./Purchase.vue"),
	},
	{
		key: "merch-purchase",
		label: "Merch & Purchase",
		shortLabel: "MP",
		path: "/merch-purchase",
		combines: ["merch", "purchase"],
		sections: { reports: "reports" },
		component: () => import("./MerchPurchase.vue"),
	},
	{
		key: "sales",
		label: "Sales",
		shortLabel: "SA",
		path: "/sales",
		sections: { production_orders: "production-orders", reports: "reports" },
		component: () => import("./Sales.vue"),
	},
	{
		key: "planning",
		label: "Planning",
		shortLabel: "PL",
		path: "/planning",
		sections: { cutting_plans: "cutting-plans", sewing_plans: "sewing-plans", finishing_plans: "finishing-plans", lots: "lots", production_orders: "production-orders", work_orders: "work-orders", reports: "reports" },
		component: () => import("./Planning.vue"),
	},
	{
		key: "pd",
		label: "PD",
		shortLabel: "PD",
		path: "/pd",
		sections: { products: "products", product_releases: "product-releases", lotwise_item_profits: "lotwise-item-profits" },
		component: () => import("./PD.vue"),
	},
	{
		key: "accounts",
		label: "Accounts",
		shortLabel: "AC",
		path: "/accounts",
		sections: { debits: "debits", purchase_invoices: "purchase-invoices", bill_tracking: "bill-tracking", reports: "reports" },
		component: () => import("./Accounts.vue"),
	},
	{
		key: "hr",
		label: "HR",
		shortLabel: "HR",
		path: "/hr",
		sections: { bill_tracking: "bill-tracking", reports: "reports" },
		component: () => import("./HR.vue"),
	},
]

/** Route paths each workspace key of `department` owns, including the sections of the departments it combines. */
export function getWorkspacePaths(department) {
	const sources = [department, ...(department.combines || []).map((key) => departments.find((item) => item.key === key))]
	const paths = {}
	for (const source of sources) {
		for (const [key, segments] of Object.entries(source.sections)) {
			paths[key] = [...(paths[key] || []), ...[segments].flat().map((segment) => `${source.path}/${segment}`)]
		}
	}
	return paths
}
