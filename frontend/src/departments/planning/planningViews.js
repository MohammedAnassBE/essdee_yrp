export const PLANNING_ROUTES = {
	cuttingPlans: "planning-cutting-plans",
	cuttingPlanNew: "planning-cutting-plan-new",
	cuttingPlan: "planning-cutting-plan",
	sewingPlans: "planning-sewing-plans",
	finishingPlans: "planning-finishing-plans",
	finishingPlan: "planning-finishing-plan",
	lots: "planning-lots",
	lot: "planning-lot",
	lotEdit: "planning-lot-edit",
	productionOrders: "planning-production-orders",
	productionOrderNew: "planning-production-order-new",
	productionOrder: "planning-production-order",
	productionOrderEdit: "planning-production-order-edit",
	workOrders: "planning-work-orders",
	workOrderNew: "planning-work-order-new",
	workOrder: "planning-work-order",
	workOrderEdit: "planning-work-order-edit",
	reports: "planning-reports",
}

export const PLANNING_WORKSPACES = [
	{
		key: "cutting_plans",
		label: "Cutting Plan",
		description: "Plans, markers, lay sheets and production movements.",
		icon: "pi pi-th-large",
		to: "/planning/cutting-plans",
	},
	{
		key: "sewing_plans",
		label: "Sewing Plan",
		description: "Unit plans, production entries and sewing progress.",
		icon: "pi pi-sitemap",
		to: "/planning/sewing-plans",
	},
	{
		key: "finishing_plans",
		label: "Finishing Plan",
		description: "Packing plans, finishing progress and dispatch commitments.",
		icon: "pi pi-box",
		to: "/planning/finishing-plans",
	},
	{
		key: "lots",
		label: "Lot",
		description: "Production lots, items and delivery dates.",
		icon: "pi pi-inbox",
		to: "/planning/lots",
	},
	{
		key: "production_orders",
		label: "Production Order",
		description: "Quantities, delivery commitments and approvals.",
		icon: "pi pi-file-edit",
		to: "/planning/production-orders",
	},
	{
		key: "work_orders",
		label: "Work Order",
		description: "Process orders, deliverables and production movements.",
		icon: "pi pi-briefcase",
		to: "/planning/work-orders",
	},
	{
		key: "reports",
		label: "Reports",
		description: "Cutting, sewing and finishing production reports.",
		icon: "pi pi-chart-bar",
		to: "/planning/reports",
	},
]

export function visiblePlanningWorkspaces(sections = {}) {
	return PLANNING_WORKSPACES.filter((item) => sections[item.key]?.can_read)
}

export const REPORT_GROUPS = [
	{ value: "cutting", label: "Cutting" },
	{ value: "sewing", label: "Sewing" },
	{ value: "finishing", label: "Finishing" },
]

export function visibleReportGroups(groups = {}) {
	return REPORT_GROUPS.filter((group) => groups[group.value] === true)
}

export function activeReportGroup(visibleGroups, requested) {
	return visibleGroups.some((group) => group.value === requested) ? requested : visibleGroups[0]?.value || ""
}

export function isCurrentRecordRequest(requestedName, currentName, sequence, currentSequence) {
	return String(requestedName || "") === String(currentName || "") && sequence === currentSequence
}
