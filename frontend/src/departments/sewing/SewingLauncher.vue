<template>
	<SewingWorkspaceShell v-slot="{ capabilities, supplier }">
		<WorkspaceLauncher
			title="Sewing"
			:items="workspaces(capabilities, supplier)"
			empty-text="No permitted Sewing workspaces"
			:skeleton-count="4"
			compact
		>
			<template #navigation><SewingBackLink to="/" label="Workspaces" /></template>
			<template #context><SewingUnitPicker /></template>
		</WorkspaceLauncher>
	</SewingWorkspaceShell>
</template>

<script setup>
import WorkspaceLauncher from "../../components/common/WorkspaceLauncher.vue"
import { documentWorkspaces } from "../fabric-store/storeWorkspaces.js"
import SewingBackLink from "./SewingBackLink.vue"
import SewingWorkspaceShell from "./SewingWorkspaceShell.vue"
import SewingUnitPicker from "./SewingUnitPicker.vue"

const definitions = [
	{ key: "plans", label: "Sewing Plan", description: "Review plans and production for a Sewing Unit.", icon: "pi pi-sitemap", path: "/sewing/plans" },
	{ key: "work_orders", label: "Work Orders", description: "Review production requirements, deliveries and receipts.", icon: "pi pi-briefcase", path: "/sewing/work-orders" },
	...documentWorkspaces("/sewing").map(({ to, ...item }) => ({ ...item, path: to })),
	{ key: "reports", label: "Reports", description: "Review production reports for a Sewing Unit.", icon: "pi pi-chart-bar", path: "/sewing/reports" },
	{ key: "attendance", label: "Attendance Report", description: "Review worker strength across all Sewing Units.", icon: "pi pi-users", path: "/sewing/attendance" },
]

function workspaces(capabilities, supplier) {
	return definitions.filter((item) => capabilities.sections?.[item.key]?.can_read).map((item) => ({
		...item,
		to: { path: item.path, query: supplier ? { supplier } : {} },
	}))
}
</script>
