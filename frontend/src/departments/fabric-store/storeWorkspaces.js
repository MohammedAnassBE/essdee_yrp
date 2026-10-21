/** Launcher cards shared by the store departments under `basePath`. */
export function storeWorkspaces(basePath, reportKeys = ["stock_balance"]) {
	return [
		{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", to: `${basePath}/work-orders` },
		{ key: "purchase_orders", label: "Purchase Orders", description: "Review purchase quantities and create Goods Received Notes.", icon: "pi pi-shopping-cart", to: `${basePath}/purchase-orders` },
		{ key: "stock_transfers", label: "Stock Transfers", description: "Create and review store stock movements and reconciliations.", icon: "pi pi-arrow-right-arrow-left", to: `${basePath}/stock-transfers` },
		{ key: "box_stickers", label: "Box Sticker Print", description: "Prepare, preview and print size-based box labels.", icon: "pi pi-tags", to: `${basePath}/box-sticker-prints` },
		{
			key: "reports",
			label: "Reports",
			description: reportKeys.includes("purchase_order_itemwise")
				? "Review stock, Purchase Order items and Lot cut quantities."
				: "Generate the current stock balance for store locations.",
			icon: "pi pi-chart-bar",
			to: `${basePath}/reports`,
		},
	]
}
