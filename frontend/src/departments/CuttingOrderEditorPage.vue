<template>
	<DepartmentPage title="Cutting Order" back-to="/cutting/orders" back-label="Cutting Orders" :show-title="false" flat full-width>
		<div class="cutting-order-editor-page erp-workspace">
			<CuttingOrderEditor :duplicate-from="duplicateFrom" @saved="saved" @cancel="router.push('/cutting/orders')" />
		</div>
	</DepartmentPage>
</template>

<script setup>
import { computed } from "vue"
import { useRoute, useRouter } from "vue-router"

import DepartmentPage from "../components/DepartmentPage.vue"
import { preserveListNavigationState } from "../router/listDocumentNavigation.js"
import CuttingOrderEditor from "./cutting/order/CuttingOrderEditor.vue"

const route = useRoute()
const router = useRouter()
const duplicateFrom = computed(() => String(route.query.duplicate_from || ""))
function saved(record) {
	if (record?.name) router.replace({ name: "cutting-order", params: { cuttingOrderId: record.name }, state: preserveListNavigationState(record.name) })
}
</script>

<style scoped>
.cutting-order-editor-page { width: 100%; min-width: 0; }
</style>
