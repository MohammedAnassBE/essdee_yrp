<template>
	<DepartmentPage title="Work Order" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width>
		<div class="fabric-work-order-editor-page erp-workspace">
			<WorkOrderEditor :key="`${workOrderId || 'new'}-${duplicateFrom}`" :name="workOrderId" :source="duplicateSource" :new-defaults="newDefaults" @saved="saved" @cancel="cancel" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import WorkOrderEditor from "./fabric-store/WorkOrderEditor.vue"
import { takeNewDocumentDefaults } from "../utils/newDocumentDefaults.js"

const props = defineProps({
	backTo: { type: String, default: "/fabric-store/work-orders" },
	backLabel: { type: String, default: "Work Orders" },
	listRouteName: { type: String, default: "fabric-work-orders" },
	viewRouteName: { type: String, default: "fabric-work-order" },
})

const route = useRoute()
const router = useRouter()
const workOrderId = computed(() => String(route.params.workOrderId || ""))
const duplicateFrom = computed(() => String(route.query.duplicate_from || ""))
const duplicateSource = computed(() => duplicateFrom.value ? { duplicate_from: duplicateFrom.value } : {})
const filterDefaults = takeNewDocumentDefaults("YRP Work Order")
const newDefaults = workOrderId.value || duplicateFrom.value ? {} : filterDefaults

function saved(record) {
	if (!record?.name) return
	router.replace({ name: props.viewRouteName, params: { workOrderId: record.name }, state: preserveListNavigationState(record.name, record.modified) })
}
function cancel() {
	if (workOrderId.value) router.push({ name: props.viewRouteName, params: { workOrderId: workOrderId.value }, state: preserveListNavigationState(workOrderId.value) })
	else if (duplicateFrom.value) router.push({ name: props.viewRouteName, params: { workOrderId: duplicateFrom.value } })
	else router.push({ name: props.listRouteName })
}
</script>

<style scoped>
.fabric-work-order-editor-page { width: 100%; min-width: 0; padding-bottom: var(--erp-space-3); }
</style>
