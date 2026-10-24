<template>
	<section class="conversion-side" :class="`conversion-side--${direction}`" :aria-label="heading">
		<header class="conversion-side__header">
			<span class="conversion-side__badge"><i :class="direction === 'from' ? 'pi pi-minus' : 'pi pi-plus'" aria-hidden="true" />{{ heading }}</span>
			<small>{{ direction === "from" ? "Issued from stock at its valuation rate" : "Received into stock with the From value" }}</small>
		</header>

		<div class="conversion-side__fields">
			<FormField class="conversion-side__wide" :field="itemField" :model-value="side.item" :required="!readOnly" :disabled="readOnly" :show-open-button="false" :show-clear="!readOnly" @update:model-value="changeItem" />
			<p v-if="loadingSchema" class="conversion-side__hint">Loading item attributes…</p>
			<template v-else-if="side.item && schema">
				<FormField v-for="field in attributeFields" :key="field.fieldname" :field="field" :model-value="side.attributes?.[field.attribute]" :disabled="readOnly" @update:model-value="updateAttribute(field.attribute, $event)" />
				<FormField v-if="primaryField" :field="primaryField" :model-value="side.primary_value" :required="!readOnly" :disabled="readOnly" @update:model-value="update({ primary_value: $event })" />
			</template>
			<FormField :field="lotField" :model-value="side.lot" :required="!readOnly" :disabled="readOnly" :show-open-button="false" :show-clear="!readOnly" @update:model-value="update({ lot: $event })" />
			<FormField :field="receivedTypeField" :model-value="side.received_type" :required="!readOnly" :disabled="readOnly" :show-open-button="false" :show-clear="!readOnly" @update:model-value="update({ received_type: $event })" />
			<FormField :field="quantityField" :model-value="side.qty" :required="!readOnly" :disabled="readOnly" @update:model-value="update({ qty: $event })" />
			<FormField v-if="schema?.secondary_uom" :field="secondaryField" :model-value="side.secondary_qty" :disabled="readOnly" @update:model-value="update({ secondary_qty: $event })" />
			<FormField class="conversion-side__wide" :field="remarksField" :model-value="side.remarks" :disabled="readOnly" @update:model-value="update({ remarks: $event })" />
		</div>

		<dl class="conversion-side__value" aria-label="Valuation">
			<div><dt>Rate</dt><dd>{{ formatAmount(rate, 4) }}</dd></div>
			<div><dt>Value</dt><dd>{{ formatAmount(amount) }}</dd></div>
		</dl>
	</section>
</template>

<script setup>
import { computed } from "vue"

import FormField from "../../../components/common/FormField.vue"
import { ITEM_FILTERS, SIDE_LABELS, formatAmount, sideAttributes, sideUom, sizeOptions, withAttribute } from "./itemConversion.js"

const props = defineProps({
	direction: { type: String, required: true },
	side: { type: Object, required: true },
	schema: { type: Object, default: null },
	loadingSchema: { type: Boolean, default: false },
	readOnly: { type: Boolean, default: false },
	rate: { type: Number, default: 0 },
	amount: { type: Number, default: 0 },
})
const emit = defineEmits(["update:side", "item-change"])

const label = computed(() => SIDE_LABELS[props.direction])
const heading = computed(() => (props.direction === "from" ? "From · consumed" : "To · produced"))
const uom = computed(() => sideUom(props.schema, props.side))
const itemField = computed(() => ({ fieldname: `${props.direction}_item`, fieldtype: "Link", options: "Item", label: `${label.value} Item`, link_filters: ITEM_FILTERS }))
const lotField = computed(() => ({ fieldname: `${props.direction}_lot`, fieldtype: "Link", options: "SD YRP Lot", label: "Lot" }))
const receivedTypeField = computed(() => ({ fieldname: `${props.direction}_received_type`, fieldtype: "Link", options: "YRP Received Type", label: "Received Type" }))
const quantityField = computed(() => ({ fieldname: `${props.direction}_qty`, fieldtype: "Float", label: `Quantity${uom.value ? ` (${uom.value})` : ""}` }))
const secondaryField = computed(() => ({ fieldname: `${props.direction}_secondary_qty`, fieldtype: "Float", label: `Secondary Quantity (${props.schema?.secondary_uom})` }))
const remarksField = computed(() => ({ fieldname: `${props.direction}_remarks`, fieldtype: "Data", label: "Remarks" }))
const attributeFields = computed(() => sideAttributes(props.schema, props.side).map((attribute, index) => ({
	fieldname: `${props.direction}_attribute_${index}`,
	attribute,
	fieldtype: "Select",
	label: attribute,
	options: (props.schema.attribute_values?.[attribute] || []).join("\n"),
})))
const primaryField = computed(() => props.schema?.primary_attribute ? {
	fieldname: `${props.direction}_primary_value`,
	fieldtype: "Select",
	label: props.schema.primary_attribute,
	options: sizeOptions(props.schema, props.side).join("\n"),
} : null)

function update(changes) { emit("update:side", { ...props.side, ...changes }) }
function updateAttribute(attribute, value) { emit("update:side", withAttribute(props.schema, props.side, attribute, value)) }
function changeItem(item) {
	update({ item: item || "", attributes: {}, primary_value: "" })
	emit("item-change", item || "")
}
</script>

<style scoped>
.conversion-side {
	--side-tone: var(--erp-attention-text);
	--side-soft: var(--erp-attention-soft);
	--side-border: var(--erp-attention-border);
	display: grid;
	align-content: start;
	gap: var(--erp-space-3);
	min-width: 0;
	padding: var(--erp-space-3);
	background: var(--erp-surface);
	border: 1px solid var(--side-border);
	border-top: 4px solid var(--side-tone);
	border-radius: var(--erp-panel-radius);
}
.conversion-side--to {
	--side-tone: var(--erp-success-text);
	--side-soft: var(--erp-success-soft);
	--side-border: color-mix(in srgb, var(--erp-success-text) 35%, var(--erp-border));
}
.conversion-side__header { display: grid; gap: 4px; }
.conversion-side__badge {
	display: inline-flex;
	width: fit-content;
	align-items: center;
	gap: 6px;
	padding: 4px 10px;
	color: var(--side-tone);
	font-weight: 800;
	letter-spacing: 0.02em;
	text-transform: uppercase;
	background: var(--side-soft);
	border-radius: var(--erp-pill-radius);
}
.conversion-side__header small, .conversion-side__hint { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); }
.conversion-side__fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--erp-space-3); }
.conversion-side__wide { grid-column: 1 / -1; }
.conversion-side__value {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--erp-space-2);
	margin: 0;
	padding: var(--erp-space-2) var(--erp-space-3);
	background: var(--side-soft);
	border-radius: var(--erp-control-radius);
}
.conversion-side__value div { display: grid; gap: 2px; }
.conversion-side__value dt { color: var(--erp-text-muted); font-size: var(--erp-font-size-caption); font-weight: 700; }
.conversion-side__value dd { margin: 0; color: var(--side-tone); font-size: 1.05rem; font-weight: 800; font-variant-numeric: tabular-nums; }
@media (max-width: 560px) { .conversion-side__fields { grid-template-columns: 1fr; } }
</style>
