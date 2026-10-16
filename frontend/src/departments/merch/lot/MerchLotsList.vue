<template>
	<DepartmentPage
		title="Lots"
		back-to="/merch"
		back-label="Merch"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section
			class="purchase-lots-page erp-workspace"
			aria-label="Merch lots"
		>
			<WorkspaceLoadError
				v-if="error"
				:message="error"
				:loading="loading"
				@retry="load"
			/>
			<div
				v-else-if="loading"
				class="purchase-lots-page__loading"
				aria-label="Loading Lots"
			>
				<ListPageSkeleton />
			</div>
			<Message
				v-else-if="!capability?.can_read"
				severity="warn"
				:closable="false"
			>
				You do not have permission to view Lots.
			</Message>
			<ListView
				v-else
				doctype="SD YRP Lot"
				title="Merch Lots"
				eyebrow="Merch"
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
					<Button
						v-if="capability?.can_create"
						label="New Lot"
						icon="pi pi-plus"
						@click="router.push({ name: MERCH_ROUTES.lotNew })"
					/>
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

import { getMerchCapabilities } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListView from "../../../components/common/ListView.vue"
import ListPageSkeleton from "../../../components/common/ListPageSkeleton.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { MERCH_ROUTES } from "../merchViews.js"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref(null)

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = (await getMerchCapabilities())?.sections?.lots || null
	} catch (reason) {
		capability.value = null
		error.value = reason?.message || "Unable to load Lots."
	} finally {
		loading.value = false
	}
}

function openLot(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: MERCH_ROUTES.lot,
		paramName: "lotId",
	})
}

onMounted(load)
</script>

<style scoped>
.purchase-lots-page {
	min-width: 0;
}
.purchase-lots-page__loading {
	display: grid;
	gap: 16px;
	padding: clamp(14px, 2vw, 22px);
}
</style>
