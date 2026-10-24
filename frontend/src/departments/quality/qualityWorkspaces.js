import { ACCOUNTS_WORKSPACES } from "../accounts/accountsViews.js"
import { documentWorkspaces } from "../fabric-store/storeWorkspaces.js"
import { merchLauncherItems } from "../merch/merchViews.js"
import { pdLauncherItems } from "../pd/pdViews.js"
import { PLANNING_WORKSPACES } from "../planning/planningViews.js"
import { departments } from "../registry.js"

export const QUALITY_COMBINED_KEYS = departments.find((department) => department.key === "quality").combinedSections

/** Quality's own cards, then the Planning, Merch, PD and Accounts cards it opens, then Reports. */
export function qualityLauncherItems() {
	const borrowed = [...PLANNING_WORKSPACES, ...merchLauncherItems(), ...pdLauncherItems(), ...ACCOUNTS_WORKSPACES]
	return [
		{ key: "inspections", label: "Essdee Quality Inspection", icon: "pi pi-verified", to: "/quality/inspections", description: "Inspect delivered colours and sizes." },
		{ key: "work_orders", label: "Work Orders", icon: "pi pi-briefcase", to: "/quality/work-orders", description: "Work Orders for quality checks." },
		...documentWorkspaces("/quality"),
		...QUALITY_COMBINED_KEYS.map((key) => borrowed.find((item) => item.key === key)),
		{ key: "reports", label: "Reports", icon: "pi pi-chart-bar", to: "/quality/reports", description: "Quality inspection and Lot Cut Quantity reports." },
	]
}
