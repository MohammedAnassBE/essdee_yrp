<template>
	<DepartmentPage title="Cutting" accent="#0b8f65" :show-title="false" flat>
		<section class="cutting-home erp-workspace erp-workspace-entry" aria-labelledby="cutting-workspace-title">
			<header class="erp-page-header">
				<div>
					<h1 id="cutting-workspace-title">Cutting</h1>
				</div>
			</header>

			<div class="workspace-grid">
				<RouterLink v-if="canReadPlans" class="workspace-card erp-card" to="/cutting/plans">
					<span class="workspace-card__icon"><i class="pi pi-th-large" aria-hidden="true"></i></span>
					<span class="workspace-card__body">
						<strong>Cutting Plans</strong>
						<small>Plans, markers, lay sheets and production movements.</small>
					</span>
					<i class="pi pi-arrow-right workspace-card__arrow" aria-hidden="true"></i>
				</RouterLink>

				<RouterLink v-if="canReadReports" class="workspace-card erp-card" to="/cutting/reports">
					<span class="workspace-card__icon workspace-card__icon--reports"><i class="pi pi-chart-bar" aria-hidden="true"></i></span>
					<span class="workspace-card__body">
						<strong>Reports</strong>
						<small>Production, cut sheet, cutting detail and stock reports.</small>
					</span>
					<i class="pi pi-arrow-right workspace-card__arrow" aria-hidden="true"></i>
				</RouterLink>
				<div v-if="!canReadPlans && !canReadReports && !loadingPermissions" class="workspace-empty erp-card">
					<i class="pi pi-lock"></i><strong>No permitted Cutting workspaces</strong>
				</div>
			</div>
		</section>
	</DepartmentPage>
</template>

<script setup>
import { RouterLink } from "vue-router"
import { computed, onMounted, ref } from "vue"

import { getCuttingReportPermissions } from "../api/cuttingReports.js"
import DepartmentPage from "../components/DepartmentPage.vue"

const loadingPermissions = ref(true)
const reportPermissions = ref({})
const canReadPlans = computed(() => Boolean(reportPermissions.value["cutting-plans"]))
const reportKeys = ["daily-production", "daily-cut-sheet", "multi-ccr", "cutting-detail", "stock-balance"]
const canReadReports = computed(() => reportKeys.some((key) => reportPermissions.value[key]))

onMounted(async () => {
	try {
		reportPermissions.value = await getCuttingReportPermissions() || {}
	} catch {
		reportPermissions.value = {}
	} finally {
		loadingPermissions.value = false
	}
})

</script>

<style scoped>
.cutting-home {
	max-width: 1120px;
	margin: 0 auto;
	padding: 24px 8px;
}

.workspace-grid {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 16px;
}

.workspace-card {
	display: grid;
	grid-template-columns: auto minmax(0, 1fr) auto;
	align-items: center;
	min-height: 144px;
	padding: 22px;
	transition: border-color var(--erp-transition-fast), box-shadow var(--erp-transition-fast), transform var(--erp-transition-fast);
}

.workspace-card:hover,
.workspace-card:focus-visible {
	border-color: color-mix(in srgb, var(--erp-accent) 38%, var(--erp-border));
	box-shadow: 0 14px 34px rgb(30 64 48 / 11%);
	transform: translateY(-2px);
}

.workspace-card__icon {
	display: grid;
	width: 52px;
	height: 52px;
	margin-right: 17px;
	color: var(--erp-accent);
	font-size: 1.2rem;
	background: var(--erp-accent-soft);
	border: 1px solid color-mix(in srgb, var(--erp-accent) 16%, var(--erp-border));
	border-radius: var(--erp-panel-radius);
	place-items: center;
}

.workspace-card__icon--reports {
	color: var(--erp-accent);
	background: var(--erp-accent-soft);
	border-color: color-mix(in srgb, var(--erp-accent) 16%, var(--erp-border));
}

.workspace-card__body {
	display: flex;
	min-width: 0;
	flex-direction: column;
}

.workspace-card__body strong {
	color: var(--erp-text);
	font-size: 1.15rem;
	font-weight: 720;
}

.workspace-card__body small {
	max-width: 370px;
	margin-top: 7px;
	color: var(--erp-text-muted);
	font-size: var(--erp-font-size-caption);
	line-height: 1.5;
}

.workspace-card__arrow {
	margin-left: 14px;
	color: var(--erp-accent);
	font-size: 1rem;
	transition: transform 160ms ease;
}

.workspace-card:hover .workspace-card__arrow { transform: translateX(3px); }
.workspace-empty { display: grid; min-height: 140px; color: #6d7b73; place-items: center; align-content: center; gap: 9px; }
.workspace-empty i { color: #638073; font-size: 1.2rem; }
.workspace-empty strong { color: #31473b; font-size: 0.86rem; }

@media (max-width: 760px) {
	.cutting-home { padding: 16px 2px; }
	.workspace-grid { grid-template-columns: 1fr; }
	.workspace-card { min-height: 138px; padding: 18px; }
}
</style>
