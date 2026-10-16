<template>
	<DepartmentPage title="Production Order" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<div class="ppo-editor-page erp-workspace"><ProductionOrderEditor :name="productionOrderId" @saved="saved" @cancel="router.push(backTo)" /></div>
	</DepartmentPage>
</template>

<script setup>
import { useRouter } from "vue-router"
import DepartmentPage from "../../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import ProductionOrderEditor from "./ProductionOrderEditor.vue"

const props = defineProps({
	productionOrderId: { type: String, default: "" },
	backTo: { type: String, default: "/sales/production-orders" },
	backLabel: { type: String, default: "Production Orders" },
	viewRouteName: { type: String, default: "sales-production-order" },
})
const router = useRouter()
function saved(record) { if (record?.name) router.replace({ name: props.viewRouteName, params: { productionOrderId: record.name }, state: preserveListNavigationState(record.name) }) }
</script>

<style scoped>.ppo-editor-page { width: 100%; min-width: 0; }</style>
