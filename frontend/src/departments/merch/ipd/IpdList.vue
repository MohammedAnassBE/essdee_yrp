<template>
	<DepartmentPage title="Item Production Details" back-to="/merch" back-label="Merch" :show-title="false" flat full-width inline-navigation>
		<section class="merch-ipds-page erp-workspace" aria-label="Item Production Details">
			<WorkspaceLoadError v-if="error" :message="error" :loading="loading" @retry="load" />
			<div v-else-if="loading" class="merch-ipds-page__loading" aria-label="Loading Item Production Details">
				<ListPageSkeleton />
			</div>
			<Message v-else-if="!capability?.can_read" severity="warn" :closable="false">
				You do not have permission to view Item Production Details.
			</Message>
			<ListView
				v-else
				doctype="YRP Item Production Detail"
				title="Item Production Details"
				eyebrow="Merch"
				subtitle="Style versions with sizes, packing, stitching, cutting and BOM"
				min-table-width="980px"
				search-placeholder="Search IPDs…"
				name-column-label="IPD"
				row-mark="IPD"
				status-field="approval_status"
				:status-options="IPD_STATUS_OPTIONS"
				initial-status="Not Approved"
				:default-columns="IPD_LIST_COLUMNS"
				:column-labels="{ tech_pack_version: 'Tech Pack', pattern_version: 'Pattern', primary_item_attribute: 'Primary', dependent_attribute: 'Dependent', approval_status: 'Status' }"
				:allow-bulk-actions="false"
				viewport-bounded
				clickable
				@row-click="openIpd"
			>
				<template #toolbar-actions>
					<template v-if="capability?.can_create">
						<Button label="New version from…" icon="pi pi-copy" severity="secondary" outlined @click="copyVisible = true" />
						<Button label="New IPD" icon="pi pi-plus" @click="router.push({ name: MERCH_ROUTES.ipdNew })" />
					</template>
				</template>
				<template #cell-approval_status="{ value }">
					<DocumentStatusBadge :label="value || 'Not Approved'" />
				</template>
			</ListView>
		</section>
		<IpdCopyDialog v-model:visible="copyVisible" @copied="openCopied" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getIpdListCapabilities } from "../../../api/merch.js"
import DepartmentPage from "../../../components/DepartmentPage.vue"
import ListPageSkeleton from "../../../components/common/ListPageSkeleton.vue"
import ListView from "../../../components/common/ListView.vue"
import WorkspaceLoadError from "../../../components/common/WorkspaceLoadError.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../../router/listDocumentNavigation.js"
import { IPD_LIST_COLUMNS, IPD_STATUS_OPTIONS, MERCH_ROUTES, ipdEditRoute } from "../merchViews.js"
import IpdCopyDialog from "./IpdCopyDialog.vue"

const router = useRouter()
const loading = ref(true)
const error = ref("")
const capability = ref(null)
const copyVisible = ref(false)

async function load() {
	loading.value = true
	error.value = ""
	try {
		capability.value = await getIpdListCapabilities()
	} catch (reason) {
		capability.value = null
		error.value = reason?.message || "Unable to load Item Production Details."
	} finally {
		loading.value = false
	}
}

function openIpd(row, snapshot) {
	return openListDocument(router, row, snapshot, { routeName: MERCH_ROUTES.ipd, paramName: "ipdId" })
}

function openCopied(name) {
	return router.push(ipdEditRoute(name))
}

onMounted(load)
</script>

<style scoped>
.merch-ipds-page {
	min-width: 0;
}
.merch-ipds-page__loading {
	display: grid;
	gap: 16px;
	padding: clamp(14px, 2vw, 22px);
}
</style>
