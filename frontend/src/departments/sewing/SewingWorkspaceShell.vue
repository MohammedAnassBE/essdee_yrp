<template>
	<DepartmentPage
		:title="title"
		accent="#0a7f5a"
		:back-to="backTo"
		:back-label="section ? 'Sewing' : 'Workspaces'"
		:show-title="false"
		flat
	>
		<section class="sewing-workspace-shell erp-workspace" :aria-label="title" :aria-busy="loading">
			<header v-if="section" class="erp-page-header">
				<div>
					<p class="erp-page-header__eyebrow">Sewing workspace</p>
					<h1>{{ title }}</h1>
				</div>
				<SewingUnitPicker v-if="section !== 'attendance'" />
			</header>
			<div v-else class="sewing-workspace-shell__unit"><SewingUnitPicker /></div>
			<div v-if="loading" class="sewing-workspace-shell__loading" role="status">
				<span class="sewing-workspace-shell__status">Loading Sewing workspace</span>
				<Skeleton v-for="index in section ? 1 : 3" :key="index" height="124px" />
			</div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="section && !capability?.can_read" severity="warn" :closable="false">
				You do not have permission to view {{ title }}.
			</Message>
			<Message v-else-if="section && section !== 'attendance' && !supplier" severity="info" :closable="false">
				Select a Sewing Unit to view {{ title }}.
			</Message>
			<slot v-else :capabilities="capabilities" :capability="capability" :supplier="supplier" />
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
import SewingUnitPicker from "./SewingUnitPicker.vue"
import { useSewingContext } from "./useSewingContext.js"

const props = defineProps({
	title: { type: String, default: "Sewing" },
	section: { type: String, default: "" },
})
const { supplier } = useSewingContext()
const router = useRouter()
const capabilities = ref({})
const capability = computed(() => capabilities.value.sections?.[props.section])
const backTo = computed(() => props.section
	? router.resolve({ path: "/sewing", query: supplier.value ? { supplier: supplier.value } : {} }).fullPath
	: "/")
const loading = ref(true)
const error = ref("")
let capabilityGeneration = 0

// Capabilities are session-wide, so a unit change must not discard this load.
// Scoped data consumers use the Sewing context's request generation instead.
async function load() {
	const generation = ++capabilityGeneration
	loading.value = true
	error.value = ""
	try {
		const payload = await getSewingCapabilities() || {}
		if (generation === capabilityGeneration) capabilities.value = payload
	} catch (reason) {
		if (generation === capabilityGeneration) {
			capabilities.value = {}
			error.value = reason?.message || "Unable to load the Sewing workspace."
		}
	} finally {
		if (generation === capabilityGeneration) loading.value = false
	}
}

onMounted(load)
onUnmounted(() => { capabilityGeneration++ })
</script>

<style scoped>
.sewing-workspace-shell { width: 100%; max-width: 1320px; min-width: 0; margin: 0 auto; padding: 2px 8px var(--erp-space-5); }
.sewing-workspace-shell__unit { display: flex; justify-content: flex-end; padding-top: var(--erp-space-3); }
.sewing-workspace-shell__loading { position: relative; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--erp-space-4); padding-top: var(--erp-space-5); }
.sewing-workspace-shell__status { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); }
.sewing-workspace-shell :deep(.workspace-launcher) { padding-inline: 0; }
@media (max-width: 760px) {
	.sewing-workspace-shell { padding-inline: 2px; }
	.sewing-workspace-shell__unit { justify-content: flex-start; }
	.sewing-workspace-shell__loading { grid-template-columns: 1fr; }
}
</style>
