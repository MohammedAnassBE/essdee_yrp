import { documentWorkspaces } from "../fabric-store/storeWorkspaces.js"
import { PLANNING_ROUTES } from "./planningRoutes.js"

export { PLANNING_ROUTES }

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
	...documentWorkspaces("/planning"),
	{
		key: "dispatches",
		label: "Finishing Plan Dispatch",
		description: "Dispatch packed boxes from several Finishing Plans together.",
		icon: "pi pi-truck",
		to: "/planning/dispatches",
	},
	{
		key: "stock_transfers",
		label: "Stock Transfers",
		description: "Stock Update, Stock Reconciliation, Stock Entry and Lot Transfer.",
		icon: "pi pi-arrow-right-arrow-left",
		to: "/planning/stock-transfers",
	},
	{
		key: "box_stickers",
		label: "Box Sticker Print",
		description: "Prepare, preview and print size-based box labels.",
		icon: "pi pi-tags",
		to: "/planning/box-sticker-prints",
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

export const PLANNING_PRODUCTION_REPORTS = [
	{ key: "work_order", value: "work-order", label: "Work Order", icon: "pi pi-briefcase" },
	{ key: "dispatch_percentage", value: "dispatch-percentage", label: "Dispatch Percentage", icon: "pi pi-percentage" },
	{ key: "work_order_pending", value: "work-order-pending", label: "Work Order Pending", icon: "pi pi-hourglass" },
	{ key: "finishing_plan", value: "finishing-plan", label: "Finishing Plan Report", icon: "pi pi-table" },
	{ key: "inward_quantity", value: "inward-quantity", label: "Inward Quantity", icon: "pi pi-sign-in" },
	{ key: "inhouse_quantity", value: "inhouse-quantity", label: "In-house Quantity", icon: "pi pi-building" },
	{ key: "month_wise_detail", value: "month-wise-detail", label: "Month-wise Detail", icon: "pi pi-calendar" },
	{ key: "process_pending", value: "process-pending", label: "Process Pending", icon: "pi pi-clock" },
	{ key: "size_wise_stock", value: "size-wise-stock", label: "Size-wise Stock", icon: "pi pi-th-large" },
	{ key: "colour_wise_diff", value: "colour-wise-diff", label: "Colour-wise Diff", icon: "pi pi-palette" },
	{ key: "work_in_progress", value: "work-in-progress", label: "Work In Progress", icon: "pi pi-chart-line" },
	{ key: "multi_ccr", value: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter" },
	{ key: "ppo_report", value: "ppo-report", label: "PPO Report", icon: "pi pi-file" },
	{ key: "work_order_bulk_close", value: "work-order-bulk-close", label: "Work Order Bulk Close", icon: "pi pi-lock" },
]

export function visibleProductionReports(reports = {}) {
	return PLANNING_PRODUCTION_REPORTS.filter((report) => reports[report.key]?.can_read === true)
}

export function isCurrentRecordRequest(requestedName, currentName, sequence, currentSequence) {
	return String(requestedName || "") === String(currentName || "") && sequence === currentSequence
}
