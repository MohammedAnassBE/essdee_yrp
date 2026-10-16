<template>
	<DepartmentPage title="LaySheet Planner" back-to="/cutting/lay-sheet-planner" back-label="LaySheet Planner" :show-title="false" flat full-width>
		<section class="planner-new erp-workspace erp-card erp-editor-shell">
			<header class="erp-editor-header"><div><span>New document</span><h1>New LaySheet Plan</h1></div><div class="planner-new__actions erp-editor-actions"><Button label="Cancel" icon="pi pi-times" severity="secondary" text :disabled="saving" @click="router.push('/cutting/lay-sheet-planner')" /><Button v-if="payload.actions?.can_edit_inputs" label="Save" icon="pi pi-save" :loading="saving" :disabled="saving || !plannerInputs?.canSave" @click="plannerInputs?.save()" /></div></header>
			<WorkspaceLoadError v-if="loadFailed" title="LaySheet Planner unavailable" :message="error" :loading="loading" @retry="load" />
			<div v-if="loading" class="planner-new__loading"><Skeleton height="480px" /></div>
			<PlannerInputs v-else-if="!loadFailed" ref="plannerInputs" :record="payload.record" :editable="payload.actions?.can_edit_inputs" :saving="saving" @save="save" />
		</section>
		<DocumentErrorDialog :message="actionError" title="LaySheet Plan was not saved" @dismiss="actionError = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Skeleton from "primevue/skeleton"
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getLaySheetPlannerEditor, saveLaySheetPlanner } from "../api/cuttingLaySheetPlanner.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import WorkspaceLoadError from "../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../components/documents/DocumentErrorDialog.vue"
import PlannerInputs from "./cutting/planner/PlannerInputs.vue"

const router = useRouter()
const payload = ref({})
const loading = ref(true)
const saving = ref(false)
const error = ref("")
const actionError = ref("")
const plannerInputs = ref(null)
const loadFailed = computed(() => Boolean(error.value && !payload.value?.record))
async function load() {
	loading.value = true
	error.value = ""
	try { payload.value = await getLaySheetPlannerEditor() }
	catch (reason) { error.value = reason?.message || "Unable to start a LaySheet Plan." }
	finally { loading.value = false }
}
onMounted(load)
async function save(values) {
	saving.value = true; actionError.value = ""
	try { const saved = await saveLaySheetPlanner(values); const name = saved?.record?.name; if (name) router.replace({ name: "cutting-lay-sheet-planner", params: { plannerId: name } }) }
	catch (reason) { actionError.value = reason?.message || "Unable to save the LaySheet Plan." }
	finally { saving.value = false }
}
</script>

<style scoped>
.planner-new { width: 100%; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); }.planner-new > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.planner-new h1 { margin: 3px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-title); }.planner-new__actions { display: flex; align-items: center; gap: 6px; }.planner-new > :deep(.p-message) { margin-top: 10px; }.planner-new__loading { padding-block: var(--erp-space-4); }
</style>
