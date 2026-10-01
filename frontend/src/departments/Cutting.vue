<template>
	<DepartmentPage title="Cutting" accent="#0b8f65" :show-title="false" flat>
		<section class="cutting-home erp-workspace" aria-labelledby="cutting-workspace-title">
			<header class="erp-page-header">
				<div>
					<p class="erp-page-header__eyebrow">Manufacturing workspace</p>
					<h1 id="cutting-workspace-title">Cutting</h1>
					<p class="erp-page-header__description">
						Plan and execute cutting operations, or open production reports for verified shop-floor analysis.
					</p>
				</div>
			</header>

			<div class="workspace-grid">
				<RouterLink v-if="canReadPlans" class="workspace-card erp-card" to="/cutting/plans">
					<span class="workspace-card__icon"><i class="pi pi-th-large" aria-hidden="true"></i></span>
					<span class="workspace-card__body">
						<span class="workspace-card__label">Operations</span>
						<strong>Cutting Plans</strong>
						<small>Plans, markers, lay sheets, cut panel movements and stock transactions.</small>
					</span>
					<i class="pi pi-arrow-right workspace-card__arrow" aria-hidden="true"></i>
				</RouterLink>

				<RouterLink v-if="canReadReports" class="workspace-card erp-card" to="/cutting/reports">
					<span class="workspace-card__icon workspace-card__icon--reports"><i class="pi pi-chart-bar" aria-hidden="true"></i></span>
					<span class="workspace-card__body">
						<span class="workspace-card__label">Analytics</span>
						<strong>Reports</strong>
						<small>Daily production, cut sheets, Multi CCR, cutting details and stock balance.</small>
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
	max-width: 1060px;
	margin: 0 auto;
	padding: 28px 8px;
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
	min-height: 166px;
	padding: 24px;
	transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.workspace-card:hover,
.workspace-card:focus-visible {
	border-color: #abd2bf;
	box-shadow: 0 14px 36px rgb(25 68 46 / 12%);
	transform: translateY(-2px);
}

.workspace-card__icon {
	display: grid;
	width: 52px;
	height: 52px;
	margin-right: 17px;
	color: #087654;
	font-size: 1.2rem;
	background: #e4f5ec;
	border: 1px solid #d1eadc;
	border-radius: 13px;
	place-items: center;
}

.workspace-card__icon--reports {
	color: #2d638c;
	background: #e9f2f8;
	border-color: #d9e8f2;
}

.workspace-card__body {
	display: flex;
	min-width: 0;
	flex-direction: column;
}

.workspace-card__label {
	margin-bottom: 6px;
	color: #688076;
	font-size: 0.68rem;
	font-weight: 800;
	letter-spacing: 0.09em;
	text-transform: uppercase;
}

.workspace-card__body strong {
	color: #1a3026;
	font-size: 1.15rem;
	font-weight: 780;
}

.workspace-card__body small {
	max-width: 370px;
	margin-top: 7px;
	color: #6a7b73;
	font-size: 0.8rem;
	line-height: 1.5;
}

.workspace-card__arrow {
	margin-left: 14px;
	color: #0b8f65;
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
