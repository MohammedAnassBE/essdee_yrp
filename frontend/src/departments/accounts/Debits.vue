<template>
	<DepartmentPage title="Debits" back-to="/accounts" back-label="Accounts" flat full-width>
		<ListView doctype="YRP Debit" title="Debits" :default-columns="['work_order', 'debit_no', 'debit_value', 'status']" :allow-bulk-actions="false" clickable @row-click="openDebit" />
		<Dialog v-model:visible="visible" modal header="Debit" class="erp-dialog--md">
			<div v-if="loading">Loading debit…</div>
			<template v-else-if="record"><DocumentStatusBadge :label="record.status" :docstatus="record.docstatus" /><dl><template v-for="field in fields" :key="field"><dt>{{ field.replaceAll('_', ' ') }}</dt><dd>{{ record[field] || '—' }}</dd></template></dl><Button v-if="record.work_order" label="Open Work Order" severity="secondary" @click="openWorkOrder" /></template>
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
import { getDoc } from "../../api/frappe.js"
import DepartmentPage from "../../components/DepartmentPage.vue"
import ListView from "../../components/common/ListView.vue"
import DocumentErrorDialog from "../../components/documents/DocumentErrorDialog.vue"
import DocumentStatusBadge from "../../components/documents/DocumentStatusBadge.vue"
const route = useRoute()
const router = useRouter()
const visible = ref(false)
const loading = ref(false)
const record = ref(null)
const error = ref("")
const fields = ["name", ...debitFields.detailGroups.flatMap((group) => group.fields)]
function openDebit(row) { router.push(`/accounts/debits/${encodeURIComponent(row.name)}`) }
function openWorkOrder() { router.push(`/fabric-store/work-orders/${encodeURIComponent(record.value.work_order)}`) }
watch(() => route.params.debitId, async (name) => {
	visible.value = Boolean(name)
	record.value = null
	if (!name) return
	loading.value = true
	try { const doc = await getDoc("YRP Debit", name); if (route.params.debitId === name) record.value = doc }
	catch (reason) { error.value = reason.message }
	finally { loading.value = false }
}, { immediate: true })
watch(visible, (value) => { if (!value && route.params.debitId) router.push("/accounts/debits") })
</script>
