const SYSTEM_MANAGER_TABS = new Set(["details", "inward", "dispatch-history"])

export function hasRole(role, boot = globalThis.window?.frappe?.boot) {
	return (boot?.user?.roles || []).includes(role)
}

/** True when the alternatives tab payload has at least one lot with item rows. */
export function hasAlternativeRows(data) {
	return Object.values(data || {}).some((lot) => (lot?.details || []).some((detail) => detail?.items?.length))
}

export function getVisibleFinishingPlanTabs(tabs, { isSystemManager = false, hasAlternatives = false } = {}) {
	return tabs.filter((tab) => {
		if (SYSTEM_MANAGER_TABS.has(tab.value)) return isSystemManager
		if (tab.value === "alternatives") return hasAlternatives
		return true
	})
}

/** The requested tab when visible, else the first visible tab. */
export function getActiveFinishingPlanTab(tabs, requested) {
	return tabs.some((tab) => tab.value === requested) ? requested : tabs[0]?.value
}
