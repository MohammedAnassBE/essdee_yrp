<template>
	<DepartmentPage title="Planning Dashboard" back-to="/planning" back-label="Planning" :show-title="false" flat full-width inline-navigation>
		<section class="planning-dashboard erp-workspace" aria-label="Planning Dashboard">
			<Tabs :value="state.view" class="erp-tabs pd-tabs" @update:value="setView">
				<TabList>
					<Tab :value="DASHBOARD_VIEW">Dashboard</Tab>
					<Tab :value="TRACKING_VIEW">PPO Tracking</Tab>
				</TabList>
			</Tabs>
			<KeepAlive>
				<DashboardView v-if="state.view === DASHBOARD_VIEW" @drill="drill" />
				<PpoTrackingView v-else :filters="state.filters" :show-dispatched="state.showDispatched" :reports="reports" @update="updateTracking" />
			</KeepAlive>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Tab from "primevue/tab"
import TabList from "primevue/tablist"
import Tabs from "primevue/tabs"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getPlanningCapabilities } from "../../../api/planning.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import { visibleProductionReports } from "../planningViews.js"
import DashboardView from "./DashboardView.vue"
import PpoTrackingView from "./PpoTrackingView.vue"
import "../../../styles/lotProcessFlow.css"
import "./planningDashboard.css"
import { DASHBOARD_VIEW, TRACKING_VIEW, drillQuery, readTrackingQuery, trackingQuery } from "./routeFilters.js"

/** Planning Dashboard page: the factory-wide Dashboard and PPO Tracking tabs; tab and tracking filters live in the URL. */
const route = useRoute()
const router = useRouter()
const reports = ref([])
const state = computed(() => readTrackingQuery(route.query))

function setView(view) {
	if (view === state.value.view) return
	router.replace({ query: { ...trackingQuery(state.value), view } })
}

function updateTracking({ filters, showDispatched, replace }) {
	const location = { query: trackingQuery({ filters, showDispatched }) }
	return replace ? router.replace(location) : router.push(location)
}

async function drill(selection) {
	await router.push({ query: drillQuery(selection) })
	window.scrollTo({ top: 0 })
}

onMounted(async () => {
	try {
		reports.value = visibleProductionReports((await getPlanningCapabilities())?.sections?.reports?.production || {})
	} catch {
		reports.value = []
	}
})
</script>
