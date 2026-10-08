<template>
	<DepartmentPage title="Work Order" accent="#0a7f5a" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width>
		<div class="fabric-work-order-editor-page erp-workspace">
			<WorkOrderEditor :key="`${workOrderId || 'new'}-${duplicateFrom}`" :name="workOrderId" :source="duplicateSource" @saved="saved" @cancel="cancel" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import WorkOrderEditor from "./fabric-store/WorkOrderEditor.vue"

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

function saved(record) {
	if (!record?.name) return
	router.replace({ name: props.viewRouteName, params: { workOrderId: record.name }, state: preserveListNavigationState(record.name) })
}
function cancel() {
	if (workOrderId.value) router.push({ name: props.viewRouteName, params: { workOrderId: workOrderId.value } })
	else if (duplicateFrom.value) router.push({ name: props.viewRouteName, params: { workOrderId: duplicateFrom.value } })
	else router.push({ name: props.listRouteName })
}
</script>

<style scoped>
.fabric-work-order-editor-page { width: 100%; max-width: 1840px; min-width: 0; margin: 0 auto; padding: 0 clamp(2px, .7vw, 10px) var(--erp-space-3); }
@media (max-width: 620px) { .fabric-work-order-editor-page { padding-right: 0; padding-left: 0; } }
</style>
