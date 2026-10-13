<template>
	<DepartmentPage
		title="Bill Tracking"
		back-to="/hr"
		back-label="HR"
		:show-title="false"
		flat
		full-width
		inline-navigation
	>
		<section class="bill-trackings-page erp-workspace" aria-label="Bill Tracking">
			<div v-if="loading" class="bill-trackings-page__loading">
				<Skeleton height="76px" />
				<Skeleton height="420px" />
			</div>
			<WorkspaceLoadError v-else-if="loadError" :message="loadError" :loading="loading" @retry="load" />
			<Message v-else-if="!capability?.can_read" severity="warn" :closable="false">
				You do not have permission to view Bill Tracking.
			</Message>
			<template v-else>
				<Message v-if="bulkSummary" severity="success" closable @close="bulkSummary = ''">
					{{ bulkSummary }}
				</Message>
				<ListView
					ref="listView"
					doctype="YRP Bill Tracking"
					title="Bill Tracking"
					eyebrow="HR"
					subtitle="Vendor bills from receipt through assignment and invoicing"
					search-placeholder="Search Bill Tracking…"
					name-column-label="Bill Tracking"
					row-mark="BT"
					min-table-width="1080px"
					status-field="form_status"
					:status-options="BILL_TRACKING_STATUS_OPTIONS"
					:default-columns="BILL_TRACKING_LIST_COLUMNS"
					:column-labels="{ form_status: 'Status' }"
					:filters="listFilters"
					:selectable="canAssign"
					:allow-bulk-actions="false"
					viewport-bounded
					clickable
					@selection-change="selectedRows = $event"
					@row-click="openBillTracking"
				>
					<template #toolbar-actions>
						<Button
							label="Assigned to me"
							icon="pi pi-user"
							severity="secondary"
							:outlined="!assignedOnly"
							:loading="loadingDepartments"
							:aria-pressed="assignedOnly"
							@click="toggleAssignedOnly"
						/>
						<Button
							v-if="canAssign"
							label="Assign Selected"
							icon="pi pi-send"
							severity="secondary"
							outlined
							:disabled="!selectedRows.length"
							@click="bulkAssignVisible = true"
						/>
						<Button
							v-if="capability.can_create"
							label="New Bill"
							icon="pi pi-plus"
							@click="createBillTracking"
						/>
					</template>
					<template #cell-form_status="{ value }">
						<DocumentStatusBadge :label="value || 'Open'" />
					</template>
				</ListView>
			</template>
		</section>

		<BillTrackingAssignDialog
			v-model:visible="bulkAssignVisible"
			:busy="bulkAssigning"
			bulk
			@assign="assignSelected"
		/>
		<DocumentErrorDialog
			:message="bulkError"
			title="Selected bills could not be assigned"
			@dismiss="bulkError = ''"
		/>
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Message from "primevue/message"
import Skeleton from "primevue/skeleton"
import { useToast } from "primevue/usetoast"
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import {
	bulkAssignBills,
	getHrCapabilities,
	getUserDepartments,
} from "../../api/hr.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import WorkspaceLoadError from "../../components/common/WorkspaceLoadError.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { openListDocument } from "../../router/listDocumentNavigation.js"
import BillTrackingAssignDialog from "./components/BillTrackingAssignDialog.vue"
import {
	BILL_TRACKING_LIST_COLUMNS,
	BILL_TRACKING_STATUS_OPTIONS,
	assignedToMeFilters,
	bulkAssignSummary,
} from "./hrViews.js"

const router = useRouter()
const toast = useToast()
const listView = ref(null)
const loading = ref(true)
const loadError = ref("")
const capability = ref(null)
const assignedOnly = ref(false)
const assignedDepartments = ref([])
const loadingDepartments = ref(false)
const selectedRows = ref([])
const bulkAssignVisible = ref(false)
const bulkAssigning = ref(false)
const bulkSummary = ref("")
const bulkError = ref("")

const listFilters = computed(() => assignedOnly.value
	? assignedToMeFilters(assignedDepartments.value) || []
	: [])
const canAssign = computed(() => hasDoctypePermission("write"))

function hasDoctypePermission(permission) {
	const user = window.frappe?.boot?.user || {}
	const sessionUser = window.frappe?.session?.user || user.name || user.email
	if (sessionUser === "Administrator") return true
	const allowed = user[`can_${permission}`]
	return Array.isArray(allowed) && allowed.includes("YRP Bill Tracking")
}

async function load() {
	loading.value = true
	loadError.value = ""
	try {
		capability.value = (await getHrCapabilities())?.sections?.bill_tracking || null
	} catch (reason) {
		capability.value = null
		loadError.value = reason?.message || "Unable to load Bill Tracking."
	} finally {
		loading.value = false
	}
}

async function toggleAssignedOnly() {
	if (assignedOnly.value) {
		assignedOnly.value = false
		assignedDepartments.value = []
		return
	}
	loadingDepartments.value = true
	try {
		const departments = await getUserDepartments()
		if (!Array.isArray(departments) || !departments.length) {
			toast.add({ severity: "info", summary: "You are not a member of any department.", life: 3500 })
			return
		}
		assignedDepartments.value = departments
		assignedOnly.value = true
	} catch (reason) {
		toast.add({ severity: "error", summary: "Unable to load your departments.", detail: reason?.message, life: 4500 })
	} finally {
		loadingDepartments.value = false
	}
}

async function assignSelected({ assignedTo, remarks }) {
	const names = selectedRows.value.map((row) => row.name).filter(Boolean)
	if (!names.length) return
	bulkAssigning.value = true
	bulkError.value = ""
	bulkSummary.value = ""
	try {
		const result = await bulkAssignBills(assignedTo, names, remarks) || {}
		bulkSummary.value = bulkAssignSummary(result)
		bulkAssignVisible.value = false
		await listView.value?.refresh(true)
	} catch (reason) {
		bulkError.value = reason?.message || "Unable to assign the selected bills."
	} finally {
		bulkAssigning.value = false
	}
}

function openBillTracking(row, snapshot) {
	return openListDocument(router, row, snapshot, {
		routeName: "hr-bill-tracking",
		paramName: "billTrackingId",
	})
}

function createBillTracking() {
	router.push({ name: "hr-bill-tracking-new" })
}

onMounted(load)
</script>

<style scoped>
.bill-trackings-page { display: grid; width: 100%; max-width: 1800px; min-width: 0; margin: 0 auto; gap: var(--erp-space-2); padding: 2px 0 var(--erp-space-5); }
.bill-trackings-page__loading { display: grid; gap: var(--erp-space-3); padding-top: 2px; }
.bill-trackings-page__loading :deep(.p-skeleton) { border-radius: var(--erp-panel-radius); }
</style>
