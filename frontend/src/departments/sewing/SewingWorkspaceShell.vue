<template>
	<DepartmentPage
		:title="title"
		:embedded="embedded"
		:back-to="backTo"
		:back-label="backLabel"
		:show-title="false"
		flat
		full-width
		hide-navigation
	>
		<section class="sewing-workspace-shell erp-workspace" :aria-label="title" :aria-busy="loading">
			<header v-if="section || loading || failed" class="sewing-workspace-shell__header" :class="{ 'sewing-workspace-shell__header--embedded': embedded }">
				<div v-if="!embedded" class="sewing-workspace-shell__title"><SewingBackLink :to="backTo" :label="backLabel" /><h1>{{ title }}</h1></div>
				<SewingUnitPicker v-if="section !== 'attendance'" />
			</header>
			<div v-if="loading" class="sewing-workspace-shell__loading" role="status">
				<span class="sewing-workspace-shell__status">Loading Sewing workspace</span>
				<Skeleton v-for="index in section ? 1 : 4" :key="index" height="124px" />
			</div>
			<WorkspaceLoadError v-else-if="failed" message="Retry to load Sewing workspace access." :loading="loading" @retry="load" />
			<Message v-else-if="section && !capability?.can_read" severity="warn" :closable="false">
				You do not have permission to view {{ title }}.
			</Message>
			<Message v-else-if="section && section !== 'attendance' && !supplier" severity="info" :closable="false">
				Select a Sewing Unit to view {{ title }}.
			</Message>
			<slot v-else :capabilities="capabilities" :capability="capability" :supplier="supplier" />
			<DocumentErrorDialog :message="error" @dismiss="error = ''" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, onUnmounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getSewingCapabilities } from "../../api/sewing.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import SewingBackLink from "./SewingBackLink.vue"
import SewingUnitPicker from "./SewingUnitPicker.vue"
import { useSewingContext } from "./useSewingContext.js"

const props = defineProps({
	title: { type: String, default: "Sewing" },
	section: { type: String, default: "" },
	backTo: { type: String, default: "" },
	backLabel: { type: String, default: "" },
	embedded: { type: Boolean, default: false },
})
const { supplier } = useSewingContext()
const router = useRouter()
const capabilities = ref({})
const capability = computed(() => capabilities.value.sections?.[props.section])
const backTo = computed(() => props.backTo || (props.section
	? router.resolve({ path: "/sewing", query: supplier.value ? { supplier: supplier.value } : {} }).fullPath
	: "/"))
const backLabel = computed(() => props.backLabel || (props.section ? "Sewing" : "Workspaces"))
const loading = ref(true)
const error = ref("")
const failed = ref(false)
let capabilityGeneration = 0

// Capabilities are session-wide, so a unit change must not discard this load.
// Scoped data consumers use the Sewing context's request generation instead.
async function load() {
	const generation = ++capabilityGeneration
	loading.value = true
	error.value = ""
	try {
		const payload = await getSewingCapabilities() || {}
		if (generation === capabilityGeneration) { capabilities.value = payload; failed.value = false }
	} catch (reason) {
		if (generation === capabilityGeneration) {
			capabilities.value = {}
			error.value = reason?.message || "Unable to load the Sewing workspace."
			failed.value = true
		}
	} finally {
		if (generation === capabilityGeneration) loading.value = false
	}
}

onMounted(load)
onUnmounted(() => { capabilityGeneration++ })
</script>

<style scoped>
.sewing-workspace-shell { width: 100%; max-width: none; min-width: 0; margin: 0; padding: 0 4px var(--erp-space-4); }
.sewing-workspace-shell__header { display: flex; align-items: center; justify-content: space-between; gap: var(--erp-space-4); margin-bottom: var(--erp-space-3); }
.sewing-workspace-shell__title { display: flex; min-width: 0; align-items: center; gap: var(--erp-space-3); }
.sewing-workspace-shell__header--embedded { justify-content: flex-end; }
.sewing-workspace-shell__title h1 { margin: 0; color: var(--erp-text); font-size: clamp(1.45rem, 2vw, 1.8rem); font-weight: var(--erp-font-weight-bold); letter-spacing: -0.035em; line-height: 1.1; }
.sewing-workspace-shell__header .sewing-unit-picker { flex: 0 1 380px; }
.sewing-workspace-shell__loading { position: relative; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-4); padding-top: var(--erp-space-4); }
.sewing-workspace-shell__status { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
.sewing-workspace-shell :deep(.workspace-launcher) {
	width: 100%;
	max-width: 1320px;
	margin-inline: auto;
	padding-inline: 8px;
}
@media (max-width: 760px) {
	.sewing-workspace-shell { padding-inline: 2px; }
	.sewing-workspace-shell__header { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--erp-space-2); }
	.sewing-workspace-shell__header .sewing-unit-picker { width: 100%; max-width: none; }
	.sewing-workspace-shell__loading { grid-template-columns: 1fr; }
}
</style>
