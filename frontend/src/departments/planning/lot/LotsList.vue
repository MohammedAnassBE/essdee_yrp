<template>
	<DepartmentPage
		title="Lots"
		back-to="/planning"
		back-label="Planning"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="planning-lots-page erp-workspace" aria-label="Planning lots">
			<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
			<div v-else-if="loading" class="planning-lots-page__loading" aria-label="Loading Lots">
				<Skeleton height="180px" />
				<Skeleton height="320px" />
			</div>
			<Message v-else-if="!capability" severity="warn" :closable="false">
				You do not have permission to view Lots.
			</Message>
			<ListView
				v-else
				doctype="SD YRP Lot"
				title="Lots"
				eyebrow="Planning"
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
				<template #cell-status="{ value }">
					<DocumentStatusBadge :label="value || 'Open'" />
				</template>
			</ListView>
		</section>
	</DepartmentPage>
</template>

<script setup>
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getPlanningCapabilities } from "../../../api/planning.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListView from "../../../components/common/ListView.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { PLANNING_ROUTES } from "../planningViews.js"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref(null)

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = (await getPlanningCapabilities())?.sections?.lots || null
	} catch (reason) {
		capability.value = null
		error.value = reason?.message || "Unable to load Lots."
	} finally {
		loading.value = false
	}
}

function openLot(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: PLANNING_ROUTES.lot,
		paramName: "lotId",
	})
}

onMounted(load)
</script>

<style scoped>
.planning-lots-page {
	min-width: 0;
}
.planning-lots-page__loading {
	display: grid;
	gap: var(--erp-space-4);
	padding: var(--erp-space-3) 0;
}
</style>
