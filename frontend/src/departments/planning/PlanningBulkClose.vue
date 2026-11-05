<template>
	<DepartmentPage title="Bulk Close" back-to="/planning" back-label="Planning" :show-title="false" flat full-width inline-navigation>
		<section class="planning-bulk-close erp-workspace" aria-label="Bulk Close">
			<Skeleton v-if="loading" height="420px" />
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<Message v-else-if="!permissions.can_read" severity="warn" :closable="false">You do not have permission to close Work Orders.</Message>
			<WorkOrderBulkClose v-else :permissions="permissions" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { onMounted, ref } from "vue"

import { getPlanningCapabilities } from "../../api/planning.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import WorkOrderBulkClose from "./reports/WorkOrderBulkClose.vue"

const loading = ref(true)
const loadError = ref("")
const permissions = ref({})

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		permissions.value = (await getPlanningCapabilities())?.sections?.bulk_close || {}
	} catch (reason) {
		permissions.value = {}
		loadError.value = reason?.message || "Unable to load Bulk Close."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.planning-bulk-close { width: 100%; min-width: 0; padding: var(--erp-space-2) 0 var(--erp-space-5); }
</style>
