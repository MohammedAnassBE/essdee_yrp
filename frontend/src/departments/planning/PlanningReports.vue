<template>
	<DepartmentPage title="Planning Reports" back-to="/planning" back-label="Planning" :show-title="false" flat full-width inline-navigation>
		<section class="planning-reports erp-workspace" :style="{ '--planning-reports-sticky-offset': `${headerHeight}px` }" aria-label="Planning Reports">
			<header ref="header" class="planning-reports__header">
				<div class="planning-reports__title"><InlinePageNavigation title-target="planning-reports-title" /><h1 id="planning-reports-title">Reports</h1></div>
				<SelectButton v-if="groups.length > 1" v-model="group" :options="groups" option-label="label" option-value="value" :allow-empty="false" aria-label="Report group" />
			</header>
			<div v-if="loading" class="planning-reports__loading"><Skeleton height="76px" /><Skeleton height="420px" /></div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<Message v-else-if="!groups.length" severity="warn" :closable="false">You do not have permission to view Planning reports.</Message>
			<CuttingReports v-else-if="group === 'cutting'" embedded :key="group" />
			<SewingReports v-else-if="group === 'sewing'" embedded :key="group" />
			<FinishingReports v-else-if="group === 'finishing'" embedded :key="group" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import SelectButton from "primevue/selectbutton"
import Skeleton from "primevue/skeleton"
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getPlanningCapabilities } from "../../api/planning.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import InlinePageNavigation from "../../components/navigation/InlinePageNavigation.vue"
import { activeReportGroup, visibleReportGroups } from "./planningViews.js"

const CuttingReports = defineAsyncComponent(() => import("../CuttingReports.vue"))
const SewingReports = defineAsyncComponent(() => import("../sewing/SewingReports.vue"))
const FinishingReports = defineAsyncComponent(() => import("../finishing/FinishingReports.vue"))
const route = useRoute()
const router = useRouter()
const loading = ref(true)
const loadError = ref("")
const groups = ref([])
const header = ref(null)
const headerHeight = ref(0)
let headerObserver
const group = computed({
	get: () => activeReportGroup(groups.value, route.query.group),
	set: (group) => router.replace({ query: { group } }),
})

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		groups.value = visibleReportGroups((await getPlanningCapabilities())?.sections?.reports?.groups)
	} catch (reason) {
		groups.value = []
		loadError.value = reason?.message || "Unable to load Planning reports."
	} finally {
		loading.value = false
	}
}

onMounted(() => {
	const updateHeaderHeight = () => { headerHeight.value = header.value.getBoundingClientRect().height }
	updateHeaderHeight()
	headerObserver = new ResizeObserver(updateHeaderHeight)
	headerObserver.observe(header.value)
	load()
})
onBeforeUnmount(() => headerObserver?.disconnect())
</script>

<style scoped>
.planning-reports { width: 100%; min-width: 0; padding: 0 0 var(--erp-space-5); }
.planning-reports__header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-4); margin-bottom: var(--erp-space-3); position: sticky; top: var(--erp-shell-header-height); z-index: var(--erp-layer-sticky); background: var(--erp-bg); padding-block: var(--erp-space-2); }
.planning-reports__title { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-3); }
.planning-reports__title h1 { margin: 0; color: var(--erp-text); font-size: clamp(1.45rem, 2vw, 1.8rem); font-weight: var(--erp-font-weight-bold); letter-spacing: -0.035em; line-height: 1.1; }
.planning-reports__loading { display: grid; gap: var(--erp-space-3); }
@media (max-width: 760px) {
	.planning-reports__header { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--erp-space-2); }
}
</style>
