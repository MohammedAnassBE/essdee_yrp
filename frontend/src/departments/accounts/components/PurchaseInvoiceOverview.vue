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
					<dd :title="String(formatDocumentOverviewValue(field))">
						<DocumentLink v-if="linkFieldTarget(field)" v-bind="linkFieldTarget(field)" :label="formatDocumentOverviewValue(field)" />
						<template v-else>{{ formatDocumentOverviewValue(field) }}</template>
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
import DocumentLink from "../../../components/common/DocumentLink.vue"
import { computed } from "vue"

import DocumentOverview from "../../../components/documents/DocumentOverview.vue"
import { linkFieldTarget } from "../../../utils/linkTarget.js"
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

</script>

<style scoped>
.purchase-invoice-overview { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(420px, 100%), 1fr)); align-items: start; gap: var(--erp-space-4); }
.purchase-invoice-overview__groups { display: contents; }
.purchase-invoice-overview__groups :deep(.document-overview__section--wide) { grid-column: 1 / -1; }
.purchase-invoice-overview__supplier { min-width: 0; overflow: hidden; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); background: var(--erp-surface); box-shadow: var(--erp-shadow-card); }
.purchase-invoice-overview__supplier > header { display: flex; align-items: center; gap: var(--erp-space-2); padding: 10px 16px; border-bottom: 1px solid var(--erp-border); background: var(--erp-surface-soft); }
.purchase-invoice-overview__supplier h2 { margin: 0; color: var(--erp-text-secondary); font-size: var(--erp-font-size-table); font-weight: var(--erp-font-weight-bold); letter-spacing: .02em; }
.purchase-invoice-overview__icon { display: inline-grid; flex: 0 0 auto; color: var(--erp-accent-ink); place-items: center; }
.purchase-invoice-overview__icon i { font-size: var(--erp-font-size-table); }
.purchase-invoice-overview__supplier dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 28px; margin: 0; padding: 16px 18px 18px; }
.purchase-invoice-overview__supplier dl > div { display: flex; min-width: 0; flex-direction: column; gap: 2px; padding: 9px 0; border-bottom: 1px solid var(--erp-border); }
.purchase-invoice-overview__supplier dt { order: 2; color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: var(--erp-font-weight-semibold); letter-spacing: .03em; text-transform: uppercase; }
.purchase-invoice-overview__supplier dd { order: 1; min-width: 0; margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-section); font-weight: var(--erp-font-weight-semibold); line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.purchase-invoice-overview__supplier a { color: var(--erp-accent-ink); text-decoration: underline dotted; text-underline-offset: 2px; }
.purchase-invoice-overview__supplier a:hover { text-decoration-style: solid; }
@media (min-width: 1400px) { .purchase-invoice-overview { grid-template-columns: repeat(auto-fill, minmax(460px, 1fr)); } }
@media (max-width: 640px) { .purchase-invoice-overview__supplier dl { grid-template-columns: 1fr; padding: 8px 14px 12px; } }
</style>
