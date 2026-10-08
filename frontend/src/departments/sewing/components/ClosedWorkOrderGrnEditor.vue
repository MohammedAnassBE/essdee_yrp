<template>
	<div class="closed-grn-editor">
		<div class="closed-grn-editor__fields">
			<FormField v-for="field in fields" :key="field.fieldname" :field="field" :model-value="values[field.fieldname]" :required="Boolean(field.reqd)" :disabled="disabled" :input-id="`closed-grn-${field.fieldname}`" @update:model-value="values[field.fieldname] = $event" />
		</div>
		<p>Enter quantities in the returned Received Type buckets. Pending quantities share one Work Order balance.</p>
		<section v-for="(group, groupIndex) in groups" :key="groupIndex" class="closed-grn-editor__group">
			<div class="closed-grn-editor__scroll" tabindex="0" role="region" :aria-label="`${group.primary_attribute || 'Item'} receipt quantities`">
				<table>
					<thead><tr><th>Item</th><th>Received Type</th><th v-for="attribute in group.attributes || []" :key="attribute">{{ attribute }}</th><th v-for="key in primaryValues(group)" :key="key">{{ key === 'default' ? 'Quantity' : key }}</th><th>UOM</th></tr></thead>
					<tbody><tr v-for="(row, index) in group.items || []" :key="index">
						<td>{{ row.name }}</td><td>{{ row.dimensions?.received_type || 'Default' }}</td><td v-for="attribute in group.attributes || []" :key="attribute">{{ row.attributes?.[attribute] }}</td>
						<td v-for="key in primaryValues(group)" :key="key" class="closed-grn-editor__quantity">
							<input v-if="row.values?.[key]?.ref_docname" v-model.number="row.values[key].qty" type="number" min="0" step="0.001" :aria-label="`${row.dimensions?.received_type || 'Default'} row ${index + 1} ${key} received quantity`" :disabled="disabled" />
							<span v-else>0</span>
							<small v-if="row.values?.[key]?.ref_docname">Pending {{ row.values[key].pending_quantity }}<br />Limit {{ row.values[key].max_receivable_quantity }}</small>
						</td><td>{{ row.default_uom }}</td>
					</tr></tbody>
				</table>
			</div>
		</section>
	</div>
</template>

<script setup>
import { computed } from "vue"
import FormField from "../../../components/common/FormField.vue"

const props = defineProps({ groups: { type: Array, required: true }, values: { type: Object, required: true }, namingField: { type: Object, required: true }, disabled: { type: Boolean, default: false } })
const fields = computed(() => [
	{ ...props.namingField, label: "Naming Series", reqd: 1 },
	...[['posting_date', 'Posting Date', 'Date', 1], ['posting_time', 'Posting Time', 'Time', 1], ['delivery_date', 'Delivery Date', 'Date', 1], ['supplier_document_no', 'Supplier Document Number', 'Data', 1], ['supplier_document_date', 'Supplier Document Date', 'Date', 1], ['vehicle_no', 'Vehicle Number', 'Data', 1], ['dc_no', 'DC Number', 'Data', 0], ['comments', 'Comments', 'Small Text', 0]].map(([fieldname, label, fieldtype, reqd]) => ({ fieldname, label, fieldtype, reqd })),
])
function primaryValues(group) { return group.primary_attribute ? group.primary_attribute_values || [] : ["default"] }
</script>

<style scoped>
.closed-grn-editor { min-width: 0; max-width: 100%; }
.closed-grn-editor__fields { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-block: 14px; }
.closed-grn-editor__fields > * { min-width: 0; }
.closed-grn-editor__fields > :last-child { grid-column: 1 / -1; }
p { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); margin: 12px 0; }
.closed-grn-editor__group { min-width: 0; max-width: 100%; border: 1px solid var(--erp-border); border-radius: var(--erp-panel-radius); margin-bottom: 12px; overflow: hidden; }
.closed-grn-editor__scroll { max-width: 100%; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: var(--erp-font-size-caption); }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--erp-border); text-align: left; white-space: nowrap; }
th { background: var(--erp-surface-soft); font-weight: 650; }
input { width: 90px; min-height: 36px; border: 1px solid var(--erp-border); border-radius: 4px; padding: 6px 8px; background: var(--erp-surface); color: var(--erp-text); font: inherit; }
input:focus-visible { outline: 2px solid var(--erp-accent); outline-offset: 2px; }
input:disabled { opacity: .65; }
small { display: block; color: var(--erp-text-muted); font-size: 10px; margin-top: 5px; line-height: 1.4; }
@media (max-width: 1050px) { .closed-grn-editor__fields { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) {
	.closed-grn-editor__fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
	.closed-grn-editor__fields :deep(.erp-date-time-field .p-inputtext) { font-size: 14px; padding-inline: 8px; }
	.closed-grn-editor__fields :deep(.p-datepicker-dropdown) { width: 32px; flex-shrink: 0; }
}
@media (max-width: 360px) { .closed-grn-editor__fields { grid-template-columns: minmax(0, 1fr); } }
</style>
