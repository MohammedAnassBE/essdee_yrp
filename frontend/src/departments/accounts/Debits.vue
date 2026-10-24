<template>
	<DepartmentPage title="Debits" back-to="/accounts" back-label="Accounts" flat full-width>
		<ListView v-if="isListInLayout" doctype="YRP Debit" title="Debits" :default-columns="['work_order', 'debit_no', 'debit_value', 'status']" :allow-bulk-actions="false" viewport-bounded clickable @row-click="openDebit" />
		<Dialog v-model:visible="visible" modal header="Debit" class="erp-dialog--md">
			<div v-if="loading">Loading debit…</div>
			<template v-else-if="record"><DocumentStatusBadge :label="record.status" :docstatus="record.docstatus" /><dl><template v-for="field in fields" :key="field"><dt>{{ field.replaceAll('_', ' ') }}</dt><dd><DocumentLink v-if="fieldTarget(field)" v-bind="fieldTarget(field)" :label="record[field] || '—'" /><template v-else>{{ record[field] || '—' }}</template></dd></template></dl><div class="debit-actions"><Button v-if="canApprove" label="Approve" icon="pi pi-check" :loading="approving" @click="approveDebit" /><Button v-if="record.work_order" label="Open Work Order" severity="secondary" @click="openWorkOrder" /><Button v-if="permissions?.create" label="Duplicate" icon="pi pi-clone" severity="secondary" outlined @click="duplicateDebit" /></div><DocumentActivity doctype="YRP Debit" :name="record.name" :record="record" /></template>
		</Dialog>
		<Dialog :visible="Boolean(duplicateFrom)" modal header="New Debit" class="erp-dialog--md" @update:visible="closeDuplicate">
			<div v-if="!draft">Loading debit…</div>
			<FormView v-else doctype="YRP Debit" title="Debit" :initial-values="draft" :include-fields="debitFields.formOrder" initial-mode="edit" show-cancel compact @saved="openDebit" @cancel="closeDuplicate(false)" />
		</Dialog>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { computed, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import debitFields from "../../config/fields/debit.js"
import { callMethod, getDoc, getMeta } from "../../api/frappe.js"
import DocumentLink from "../../components/common/DocumentLink.vue"
import { linkFieldTarget } from "../../utils/linkTarget.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import FormView from "../../components/common/FormView.vue"
import ListView from "../../components/common/ListView.vue"
import { useDocumentPermissions } from "../../composables/useDocumentPermissions.js"
import { loadDuplicateValues } from "../../composables/useDuplicateAction.js"
import DocumentActivity from "../../components/documents/DocumentActivity.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
import { getHomePath, isOutsideLayout } from "../../router/departmentLock.js"
const route = useRoute()
const router = useRouter()
const visible = ref(false)
const loading = ref(false)
const record = ref(null)
const metadata = ref({})
const error = ref("")
const isListInLayout = !isOutsideLayout("/accounts/debits")
const fields = ["name", ...debitFields.detailGroups.flatMap((group) => group.fields)]
const permissions = useDocumentPermissions(() => ["YRP Debit", record.value?.name, record.value?.docstatus])
const duplicateFrom = computed(() => String(route.query.duplicate_from || ""))
const draft = ref(null)
const canApprove = ref(false)
const approving = ref(false)
const DEBIT_METHOD = "yrp.yrp.doctype.yrp_debit.yrp_debit"
function fieldTarget(fieldname) {
	return linkFieldTarget({ ...metadata.value[fieldname], value: record.value?.[fieldname] }, record.value || {})
}
function openDebit(row) { router.push(`/accounts/debits/${encodeURIComponent(row.name)}`) }
function duplicateDebit() { router.push({ path: "/accounts/debits", query: { duplicate_from: record.value.name } }) }
function closeDuplicate(open) { if (!open) router.push(isListInLayout ? "/accounts/debits" : getHomePath()) }
watch(duplicateFrom, async (name) => {
	draft.value = null
	if (!name) return
	try {
		const values = await loadDuplicateValues("YRP Debit", route)
		if (duplicateFrom.value === name) draft.value = Object.fromEntries(debitFields.formOrder.filter((fieldname) => values[fieldname] != null).map((fieldname) => [fieldname, values[fieldname]]))
	} catch (reason) { error.value = reason.message; closeDuplicate(false) }
}, { immediate: true })
async function approveDebit() {
	approving.value = true
	try {
		await callMethod(`${DEBIT_METHOD}.approve_debit`, { name: record.value.name })
		record.value = await getDoc("YRP Debit", record.value.name)
		canApprove.value = false
	} catch (reason) { error.value = reason.message }
	finally { approving.value = false }
}
function openWorkOrder() { router.push(`/fabric-store/work-orders/${encodeURIComponent(record.value.work_order)}`) }
watch(() => route.params.debitId, async (name) => {
	visible.value = Boolean(name)
	record.value = null
	canApprove.value = false
	if (!name) return
	loading.value = true
	try {
		const [doc, metas] = await Promise.all([getDoc("YRP Debit", name), getMeta("YRP Debit")])
		if (route.params.debitId === name) {
			metadata.value = Object.fromEntries((metas.find((meta) => meta.name === "YRP Debit")?.fields || []).map((field) => [field.fieldname, field]))
			record.value = doc
			canApprove.value = doc.docstatus === 1 && doc.status === "Debit Requested" && Boolean(await callMethod(`${DEBIT_METHOD}.has_debit_approval_permission`))
		}
	}
	catch (reason) { error.value = reason.message }
	finally { loading.value = false }
}, { immediate: true })
watch(visible, (value) => { if (!value && route.params.debitId) router.push(isListInLayout ? "/accounts/debits" : getHomePath()) })
</script>

<style scoped>.debit-actions { display: flex; flex-wrap: wrap; gap: var(--erp-space-2, 8px); }</style>
