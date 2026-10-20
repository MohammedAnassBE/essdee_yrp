<template>
	<div class="purchase-invoice-header">
		<div class="purchase-invoice-header__identity">
			<h1 :id="headingId">Purchase Invoice · {{ record.name }}</h1>
			<DocumentStatusBadge
				:docstatus="record.docstatus"
				:label="record.status"
				:class="statusClass(record.status)"
			/>
		</div>
		<dl class="purchase-invoice-header__facts">
			<div><dt>Supplier</dt><dd :title="record.supplier || '—'"><DocumentLink doctype="Supplier" :name="record.supplier_link_name ?? record.supplier" :label="record.supplier || '—'" /></dd></div>
			<div><dt>Supplier Invoice No</dt><dd :title="record.bill_no || '—'">{{ record.bill_no || "—" }}</dd></div>
			<div><dt>Grand Total</dt><dd>{{ money(record.grand_total) }}</dd></div>
		</dl>
	</div>
</template>

<script setup>
import DocumentLink from "../../../components/common/DocumentLink.vue"
import DocumentStatusBadge from "../../../components/documents/DocumentStatusBadge.vue"

defineProps({
	record: { type: Object, required: true },
	headingId: { type: String, required: true },
})

function statusClass(status) {
	return `purchase-invoice-status--${String(status || "draft").toLowerCase().replaceAll(" ", "-")}`
}

function money(input) {
	if (input === null || input === undefined || input === "") return "—"
	const numericValue = Number(input)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "—"
}
</script>

<style scoped>
.purchase-invoice-header { display: flex; min-width: 0; align-items: center; justify-content: space-between; gap: 14px; padding-block: 3px; }
.purchase-invoice-header__identity { display: flex; min-width: 0; align-items: center; gap: 10px; }
.purchase-invoice-header__identity h1 { min-width: 0; overflow-wrap: anywhere; white-space: normal; margin: 0; overflow: hidden; color: var(--erp-text); font-size: clamp(18px, 1.35vw, 22px); letter-spacing: -.02em; text-overflow: ellipsis; }
.purchase-invoice-header__facts { display: flex; min-width: 0; align-items: center; margin: 0; gap: 0; }
.purchase-invoice-header__facts > div { display: grid; min-width: 100px; max-width: 210px; gap: 2px; padding: 1px 12px; border-left: 1px solid var(--erp-border); }
.purchase-invoice-header__facts dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-min); font-weight: 730; letter-spacing: .035em; text-transform: uppercase; }
.purchase-invoice-header__facts dd { margin: 0; overflow: hidden; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 700; text-overflow: ellipsis; white-space: nowrap; font-variant-numeric: tabular-nums; }
:deep(.purchase-invoice-status--draft) { color: var(--erp-warning); background: var(--erp-warning-soft); border-color: var(--erp-attention-border); }
:deep(.purchase-invoice-status--approval-initiated) { color: var(--erp-danger); background: var(--erp-danger-soft); border-color: color-mix(in srgb, var(--erp-danger) 22%, transparent); }
:deep(.purchase-invoice-status--approval-pending) { color: var(--erp-warning); background: var(--erp-warning-soft); border-color: var(--erp-attention-border); }
:deep(.purchase-invoice-status--approved) { color: var(--erp-accent-hover); background: var(--erp-success-soft); border-color: color-mix(in srgb, var(--erp-success) 18%, transparent); }
:deep(.purchase-invoice-status--submitted) { color: var(--erp-info); background: var(--erp-info-soft); border-color: color-mix(in srgb, var(--erp-info) 18%, transparent); }
:deep(.purchase-invoice-status--cancelled) { color: var(--erp-text); background: var(--erp-surface-muted); border-color: var(--erp-border-strong); }
@media (max-width: 1050px) { .purchase-invoice-header { align-items: flex-start; flex-direction: column; } .purchase-invoice-header__facts { width: 100%; } .purchase-invoice-header__facts > div:first-child { border-left: 0; padding-left: 0; } }
@media (max-width: 620px) { .purchase-invoice-header__identity { width: 100%; align-items: flex-start; flex-direction: column; } .purchase-invoice-header__facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); } .purchase-invoice-header__facts > div { min-width: 0; padding-inline: 8px; } .purchase-invoice-header__facts dd { white-space: normal; } }
</style>
