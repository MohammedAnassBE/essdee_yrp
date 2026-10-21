<template>
	<DepartmentPage title="Debits" back-to="/accounts" back-label="Accounts" flat full-width>
		<ListView v-if="isListInLayout" doctype="YRP Debit" title="Debits" :default-columns="['work_order', 'debit_no', 'debit_value', 'status']" :allow-bulk-actions="false" clickable @row-click="openDebit" />
		<Dialog v-model:visible="visible" modal header="Debit" class="erp-dialog--md">
			<div v-if="loading">Loading debit…</div>
			<template v-else-if="record"><DocumentStatusBadge :label="record.status" :docstatus="record.docstatus" /><dl><template v-for="field in fields" :key="field"><dt>{{ field.replaceAll('_', ' ') }}</dt><dd><DocumentLink v-if="fieldTarget(field)" v-bind="fieldTarget(field)" :label="record[field] || '—'" /><template v-else>{{ record[field] || '—' }}</template></dd></template></dl><Button v-if="record.work_order" label="Open Work Order" severity="secondary" @click="openWorkOrder" /></template>
		</Dialog>
		<DocumentErrorDialog :message="error" @dismiss="error = ''" />
	</DepartmentPage>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import { ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import debitFields from "../../config/fields/debit.js"
import { getDoc, getMeta } from "../../api/frappe.js"
import DocumentLink from "../../components/common/DocumentLink.vue"
import { linkFieldTarget } from "../../utils/linkTarget.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
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
function fieldTarget(fieldname) {
	return linkFieldTarget({ ...metadata.value[fieldname], value: record.value?.[fieldname] }, record.value || {})
}
function openDebit(row) { router.push(`/accounts/debits/${encodeURIComponent(row.name)}`) }
function openWorkOrder() { router.push(`/fabric-store/work-orders/${encodeURIComponent(record.value.work_order)}`) }
watch(() => route.params.debitId, async (name) => {
	visible.value = Boolean(name)
	record.value = null
	if (!name) return
	loading.value = true
	try {
		const [doc, metas] = await Promise.all([getDoc("YRP Debit", name), getMeta("YRP Debit")])
		if (route.params.debitId === name) {
			metadata.value = Object.fromEntries((metas.find((meta) => meta.name === "YRP Debit")?.fields || []).map((field) => [field.fieldname, field]))
			record.value = doc
		}
	}
	catch (reason) { error.value = reason.message }
	finally { loading.value = false }
}, { immediate: true })
watch(visible, (value) => { if (!value && route.params.debitId) router.push(isListInLayout ? "/accounts/debits" : getHomePath()) })
</script>
