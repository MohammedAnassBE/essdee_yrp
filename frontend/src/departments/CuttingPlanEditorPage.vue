<template>
	<DepartmentPage title="Cutting Plan" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width>
		<div class="cutting-plan-editor-page erp-workspace">
			<CuttingPlanEditor :initial-source="source" @saved="saved" @cancel="router.push(backTo)" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import CuttingPlanEditor from "./cutting/plan/CuttingPlanEditor.vue"

const props = defineProps({
	backTo: { type: String, default: "/cutting/plans" },
	backLabel: { type: String, default: "Cutting Plans" },
	viewRouteName: { type: String, default: "cutting-plan" },
})

const route = useRoute()
const router = useRouter()
const source = computed(() => Object.fromEntries(
	["work_order", "lot", "item"].map((key) => [key, String(route.query[key] || "")]).filter(([, value]) => value),
))

function saved(record) {
	if (!record?.name) return
	router.replace({ name: props.viewRouteName, params: { cuttingPlanId: record.name }, state: preserveListNavigationState(record.name) })
}
</script>

<style scoped>
.cutting-plan-editor-page { width: 100%; min-width: 0; }
</style>
