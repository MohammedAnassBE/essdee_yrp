<template>
	<DepartmentPage title="Quality Inspections" back-to="/quality" back-label="Quality" :show-title="false" flat full-width inline-navigation>
		<ListPageSkeleton v-if="loading" />
		<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
		<Message v-else-if="!capability.can_read" severity="warn" :closable="false">You do not have permission to view Quality Inspections.</Message>
		<ListView v-else :doctype="INSPECTION_DOCTYPE" title="Essdee Quality Inspection" eyebrow="Quality"
			:default-columns="INSPECTION_LIST_COLUMNS" status-field="result" :status-options="statusOptions"
			:allow-bulk-actions="false" full-width viewport-bounded clickable @row-click="openInspection">
			<template #toolbar-actions>
				<Button v-if="capability.can_create" label="New" icon="pi pi-plus" @click="router.push('/quality/inspections/new')" />
			</template>
			<template #cell-result="{ value }"><DocumentStatusBadge v-if="value" :label="value" :tone="resultTone(value)" /></template>
			<template v-for="(doctype, field) in linkColumns" :key="field" #[`cell-${field}`]="{ value }">
				<DocumentLink :doctype="doctype" :name="value" current-path="/web/quality/inspections" />
			</template>
		</ListView>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { getQualityCapabilities } from "../../api/quality.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import ListPageSkeleton from "../../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentLink from "../../components/common/DocumentLink.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import { INSPECTION_DOCTYPE, INSPECTION_LIST_COLUMNS, resultTone } from "./qualityViews.js"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref({})
const statusOptions = ["Pass", "Fail", "Hold"].map((value) => ({ label: value, value, tone: resultTone(value) }))
const linkColumns = { against_id: "YRP Work Order", lot: "SD YRP Lot", item: "Item", supplier: "Supplier" }

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = (await getQualityCapabilities())?.sections?.inspections || {}
	} catch (reason) {
		error.value = reason?.message || "Unable to load inspections."
	} finally {
		loading.value = false
	}
}

function openInspection(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: "quality-inspection", paramName: "inspectionId" })
}

onMounted(load)
</script>
