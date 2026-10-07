<template>
	<DepartmentPage title="LaySheet Planner" accent="#059669" back-to="/cutting/lay-sheet-planner" back-label="LaySheet Planner" :show-title="false" flat full-width>
		<section class="planner-new erp-workspace erp-card">
			<header><div><span>New document</span><h1>New LaySheet Plan</h1></div><div class="planner-new__actions"><Button label="Cancel" severity="secondary" text :disabled="saving" @click="router.push('/cutting/lay-sheet-planner')" /><Button v-if="payload.actions?.can_edit_inputs" label="Save Draft" icon="pi pi-save" :loading="saving" :disabled="saving || !plannerInputs?.canSave" @click="plannerInputs?.save()" /></div></header>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div v-if="loading" class="planner-new__loading"><Skeleton height="480px" /></div>
			<PlannerInputs v-else ref="plannerInputs" :record="payload.record" :editable="payload.actions?.can_edit_inputs" :saving="saving" @save="save" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getLaySheetPlannerEditor, saveLaySheetPlanner } from "../api/cuttingLaySheetPlanner.js"
import DepartmentPage from "../components/DepartmentPage.vue"
import PlannerInputs from "./cutting/planner/PlannerInputs.vue"

const router = useRouter()
const payload = ref({})
const loading = ref(true)
const saving = ref(false)
const error = ref("")
const plannerInputs = ref(null)
onMounted(async () => { try { payload.value = await getLaySheetPlannerEditor() } catch (reason) { error.value = reason?.message || "Unable to start a LaySheet Plan." } finally { loading.value = false } })
async function save(values) {
	saving.value = true; error.value = ""
	try { const saved = await saveLaySheetPlanner(values); const name = saved?.record?.name; if (name) router.replace({ name: "cutting-lay-sheet-planner", params: { plannerId: name } }) }
	catch (reason) { error.value = reason?.message || "Unable to save the LaySheet Plan." }
	finally { saving.value = false }
}
</script>

<style scoped>
.planner-new { width: 100%; max-width: 1500px; min-width: 0; min-height: calc(100dvh - var(--erp-shell-header-height) - 98px); margin: 0 auto; }.planner-new > header { display: flex; min-height: 70px; padding: 12px var(--erp-space-4); align-items: center; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--erp-border); }.planner-new > header span { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 720; letter-spacing: .04em; text-transform: uppercase; }.planner-new h1 { margin: 3px 0 0; color: var(--erp-text); font-size: var(--erp-font-size-title); }.planner-new__actions { display: flex; align-items: center; gap: 6px; }.planner-new > :deep(.p-message) { margin: 10px var(--erp-space-4) 0; }.planner-new__loading { padding: var(--erp-space-4); }
@media (max-width: 620px) { .planner-new > header { align-items: flex-start; flex-direction: column; }.planner-new__actions { width: 100%; }.planner-new__actions :deep(.p-button:last-child) { flex: 1; } }
</style>
