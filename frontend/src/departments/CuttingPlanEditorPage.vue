<template>
	<DepartmentPage title="Cutting Plan" accent="#079669" back-to="/cutting/plans" back-label="Cutting Plans" :show-title="false" flat full-width>
		<div class="cutting-plan-editor-page erp-workspace">
			<CuttingPlanEditor :initial-source="source" @saved="saved" @cancel="router.push('/cutting/plans')" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import CuttingPlanEditor from "./cutting/plan/CuttingPlanEditor.vue"

const route = useRoute()
const router = useRouter()
const source = computed(() => Object.fromEntries(
	["work_order", "lot", "item"].map((key) => [key, String(route.query[key] || "")]).filter(([, value]) => value),
))

function saved(record) {
	if (!record?.name) return
	router.replace({ name: "cutting-plan", params: { cuttingPlanId: record.name } })
}
</script>

<style scoped>
.cutting-plan-editor-page { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; }
</style>
