<template>
	<DepartmentPage
		title="Lots"
		back-to="/purchase"
		back-label="Purchase"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="purchase-lots-page erp-workspace" aria-label="Purchase lots">
			<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
			<Message v-else-if="!loading && !capability" severity="warn" :closable="false">
				You do not have permission to view Lots.
			</Message>
			<ListView
				v-else
				:can-read="!loading && Boolean(capability)"
				doctype="SD YRP Lot"
				title="Lots"
				eyebrow="Purchase"
				subtitle="Production lots, items and delivery dates"
				min-table-width="980px"
				search-placeholder="Search Lots…"
				name-column-label="Lot"
				row-mark="LOT"
				status-field="status"
				:status-options="['Open', 'Closed']"
				initial-status="Open"
				:default-columns="[
					'item',
					'production_order',
					'season',
					'assigned_person_name',
					'expected_delivery_date',
					'status',
				]"
				:column-labels="{
					production_order: 'Production Order',
					assigned_person_name: 'Assigned Person',
				}"
				:allow-bulk-actions="false"
				viewport-bounded
				clickable
				@row-click="openLot"
			>
				<template #toolbar-actions>
					<Button v-if="capability?.can_create" label="New Lot" icon="pi pi-plus" @click="router.push({ name: PURCHASE_ROUTES.lotNew })" />
				</template>
				<template #cell-status="{ value }">
					<DocumentStatusBadge :label="value || 'Open'" />
				</template>
			</ListView>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getPurchaseCapabilities } from "../../../api/purchase.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListView from "../../../components/common/ListView.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { PURCHASE_ROUTES } from "../purchaseViews.js"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref(null)

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = (await getPurchaseCapabilities())?.sections?.lots || null
	} catch (reason) {
		capability.value = null
		error.value = reason?.message || "Unable to load Lots."
	} finally {
		loading.value = false
	}
}

function openLot(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: PURCHASE_ROUTES.lot,
		paramName: "lotId",
	})
}

onMounted(load)
</script>

<style scoped>
.purchase-lots-page {
	min-width: 0;
}
</style>
