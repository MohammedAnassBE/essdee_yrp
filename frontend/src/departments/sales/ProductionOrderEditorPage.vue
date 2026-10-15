<template>
	<DepartmentPage title="Production Order" back-to="/sales/production-orders" back-label="Production Orders" :show-title="false" flat full-width inline-navigation>
		<div class="ppo-editor-page erp-workspace"><ProductionOrderEditor :name="productionOrderId" @saved="saved" @cancel="router.push('/sales/production-orders')" /></div>
	</DepartmentPage>
</template>

<script setup>
import { useRouter } from "vue-router"
import DepartmentPage from "../../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../../router/listDocumentNavigation.js"
import ProductionOrderEditor from "./ProductionOrderEditor.vue"

defineProps({ productionOrderId: { type: String, default: "" } })
const router = useRouter()
function saved(record) { if (record?.name) router.replace({ name: "sales-production-order", params: { productionOrderId: record.name }, state: preserveListNavigationState(record.name) }) }
</script>

<style scoped>.ppo-editor-page { width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; }</style>
