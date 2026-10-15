<template>
	<DepartmentPage title="Production Orders" :back-to="backTo" :back-label="backLabel" :show-title="false" flat full-width inline-navigation>
		<section class="sales-section erp-workspace" aria-label="Production Orders">
			<div v-if="loading" class="sales-section__loading">
				<Skeleton height="76px" />
				<Skeleton height="420px" />
			</div>
			<WorkspaceLoadError v-else-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!capability" severity="warn" :closable="false">You do not have permission to view Production Orders.</Message>
			<ProductionOrders v-else :capability="capability" :view-route-name="viewRouteName" :new-route-name="newRouteName" />
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { onMounted, ref } from "vue"

import { getSalesCapabilities } from "../../api/sales.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import ProductionOrders from "./ProductionOrders.vue"

const props = defineProps({
	backTo: { type: String, default: "/sales" },
	backLabel: { type: String, default: "Sales" },
	viewRouteName: { type: String, default: "sales-production-order" },
	newRouteName: { type: String, default: "sales-production-order-new" },
})

const loading = ref(true)
const error = ref("")
const capability = ref(null)

async function load() {
	loading.value = true
	error.value = ""
	try {
		const payload = await getSalesCapabilities() || {}
		capability.value = payload.sections?.production_orders || null
	} catch (reason) {
		error.value = reason?.message || "Unable to load Production Orders."
	} finally {
		loading.value = false
	}
}

onMounted(load)
</script>

<style scoped>
.sales-section {
	width: 100%;
	max-width: 1800px;
	min-width: 0;
	margin: 0 auto;
	padding: 2px 0 var(--erp-space-5);
}

.sales-section__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.sales-section__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
</style>
