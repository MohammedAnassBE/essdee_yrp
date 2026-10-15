<template>
	<div class="purchase-invoice-overview" aria-label="Purchase Invoice overview">
		<DocumentOverview
			class="purchase-invoice-overview__groups"
			:fields="fields"
			:definitions="invoiceDefinitions"
			aria-label="Invoice details"
			id-prefix="purchase-invoice-invoice"
		/>
		<section
			v-if="supplierFields.length"
			class="purchase-invoice-overview__supplier"
			aria-labelledby="purchase-invoice-supplier-bill"
		>
			<header>
				<div class="purchase-invoice-overview__icon" aria-hidden="true"><i class="pi pi-building" /></div>
				<h2 id="purchase-invoice-supplier-bill">Supplier bill</h2>
			</header>
			<dl>
				<div v-for="field in supplierFields" :key="field.fieldname">
					<dt>{{ field.label }}</dt>
					<dd v-if="field.fieldname === 'bill_tracking'">
						<RouterLink :to="documentRoute('YRP Bill Tracking', field.value)">{{ field.value }}</RouterLink>
					</dd>
					<dd v-else :title="String(formatDocumentOverviewValue(field))">
						{{ formatDocumentOverviewValue(field) }}
					</dd>
				</div>
			</dl>
		</section>
		<DocumentOverview
			class="purchase-invoice-overview__groups"
			:fields="fields"
			:definitions="remainingDefinitions"
			aria-label="Purchase Invoice details"
			id-prefix="purchase-invoice-details"
		/>
	</div>
</template>

<script setup>
import { computed } from "vue"

import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import { webDocumentPath } from "../../../router/webDocumentRoutes.js"
import {
	documentOverviewHasValue,
	formatDocumentOverviewValue,
} from "../../../utils/documentOverview.js"

const props = defineProps({
	fields: { type: Array, default: () => [] },
})

const invoiceDefinitions = [
	{
		key: "invoice",
		label: "Invoice",
		icon: "pi pi-file-edit",
		fields: ["against", "posting_date", "due_date"],
	},
]
const supplierFieldnames = ["billing_supplier", "bill_date", "bill_tracking", "eligibility_for_itc"]
const remainingDefinitions = [
	{
		key: "debit",
		label: "Debit",
		icon: "pi pi-minus-circle",
		fields: ["debit_type", "debit_no", "debit_value"],
	},
	{
		key: "erp-bill",
		label: "ERP bill",
		icon: "pi pi-receipt",
		fields: ["erp_inv_name", "final_amount"],
	},
	{
		key: "notes",
		label: "Notes",
		icon: "pi pi-align-left",
		fields: ["remarks"],
		wide: true,
	},
]
const supplierFields = computed(() => {
	const fieldsByName = new Map(props.fields.map((field) => [field.fieldname, field]))
	return supplierFieldnames
		.map((fieldname) => fieldsByName.get(fieldname))
		.filter((field) => field && documentOverviewHasValue(field.value))
})

function documentRoute(doctype, name) {
	return webDocumentPath(doctype, name).replace(/^\/web(?=\/)/, "")
}
</script>

<style scoped>
.purchase-invoice-overview { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: var(--erp-space-3); }
.purchase-invoice-overview__groups { display: contents; }
.purchase-invoice-overview__groups :deep(.document-overview__section--wide) { grid-column: 1 / -1; }
.purchase-invoice-overview__supplier { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: 0 7px 20px rgb(28 61 45 / 4%); }
.purchase-invoice-overview__supplier > header { display: flex; min-height: 64px; align-items: center; gap: 10px; padding: 10px 13px; border-bottom: 1px solid var(--erp-border); background: color-mix(in srgb, var(--erp-surface-soft) 78%, white); }
.purchase-invoice-overview__supplier h2 { margin: 0; color: var(--erp-text); font-size: 14px; font-weight: 760; letter-spacing: -.01em; }
.purchase-invoice-overview__icon { display: inline-grid; width: 34px; height: 34px; flex: 0 0 auto; color: var(--erp-accent-hover); border: 1px solid var(--erp-accent-border); border-radius: 9px; background: var(--erp-accent-soft); place-items: center; }
.purchase-invoice-overview__icon i { font-size: .88rem; }
.purchase-invoice-overview__supplier dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; }
.purchase-invoice-overview__supplier dl > div { display: grid; min-width: 0; min-height: 62px; align-content: center; gap: 4px; padding: 10px 13px; border-right: 1px solid var(--erp-border); border-bottom: 1px solid var(--erp-border); }
.purchase-invoice-overview__supplier dl > div:nth-child(2n) { border-right: 0; }
.purchase-invoice-overview__supplier dl > div:nth-last-child(-n + 2) { border-bottom: 0; }
.purchase-invoice-overview__supplier dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.purchase-invoice-overview__supplier dd { min-width: 0; margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; text-overflow: ellipsis; white-space: nowrap; }
.purchase-invoice-overview__supplier a { color: var(--erp-accent-hover); text-decoration: none; }
.purchase-invoice-overview__supplier a:hover { text-decoration: underline; }
@media (max-width: 760px) { .purchase-invoice-overview { grid-template-columns: 1fr; } .purchase-invoice-overview__groups :deep(.document-overview__section--wide) { grid-column: auto; } }
</style>
