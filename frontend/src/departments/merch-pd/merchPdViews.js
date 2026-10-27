import { storeWorkspaces } from "../fabric-store/storeWorkspaces.js"
import { merchLauncherItems } from "../merch/merchViews.js"
import { pdLauncherItems } from "../pd/pdViews.js"
import { departments } from "../registry.js"

export const MERCH_PD_WORKSPACE_KEYS = departments.find((department) => department.key === "merch-pd").combinedSections

/** Lot, Item Production Detail and Vendor Bill Tracking from Merch, Purchase Orders from Purchase and Lotwise Item Profit from PD. */
export function merchPdLauncherItems() {
	const items = [...merchLauncherItems(), ...storeWorkspaces("/purchase"), ...pdLauncherItems()]
	return MERCH_PD_WORKSPACE_KEYS.map((key) => items.find((item) => item.key === key))
}
