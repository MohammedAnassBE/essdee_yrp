import { storeWorkspaces } from "../fabric-store/storeWorkspaces.js"
import { merchLauncherItems } from "../merch/merchViews.js"
import { PURCHASE_REPORT_KEYS, PURCHASE_STORE_WORKSPACE_KEYS, purchaseLauncherItems } from "../purchase/purchaseViews.js"

export const MERCH_PURCHASE_REPORTS_PATH = "/merch-purchase/reports"

/** Merch cards, then the Purchase cards Merch lacks, then one combined Reports card. */
export function merchPurchaseLauncherItems() {
	const purchaseStore = storeWorkspaces("/purchase", PURCHASE_REPORT_KEYS).filter((item) => PURCHASE_STORE_WORKSPACE_KEYS.includes(item.key))
	const items = [...merchLauncherItems(), ...purchaseLauncherItems(), ...purchaseStore].filter((item) => item.key !== "reports")
	return [
		...items.filter((item, index) => items.findIndex((other) => other.key === item.key) === index),
		{
			key: "reports",
			label: "Reports",
			description: "Merch and Purchase reports in one place.",
			icon: "pi pi-chart-bar",
			to: MERCH_PURCHASE_REPORTS_PATH,
		},
	]
}
