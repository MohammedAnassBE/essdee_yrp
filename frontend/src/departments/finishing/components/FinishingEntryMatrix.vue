<template>
	<div class="finishing-scroll" role="region" tabindex="0" :aria-label="`${inputLabel} entry`">
		<table class="finishing-table finishing-entry-matrix">
			<thead>
				<tr>
					<th class="finishing-table__index">S.No</th>
					<th class="finishing-table__colour">Colour</th>
					<th v-if="payload.is_set_item">{{ payload.set_attr }}</th>
					<th class="finishing-table__type">Type</th>
					<th v-for="size in sizes" :key="size" class="erp-number">{{ size }}</th>
					<th class="erp-number">Total</th>
				</tr>
			</thead>
			<tbody v-for="(colour, index) in colours" :key="colour">
				<tr v-for="(reference, referenceIndex) in references" :key="reference.key">
					<template v-if="referenceIndex === 0">
						<td :rowspan="rowSpan" class="finishing-table__index">
							<span>{{ index + 1 }}</span>
							<input v-if="checkable" v-model="modelValue[colour].checked" type="checkbox" class="finishing-entry-matrix__check" :aria-label="`Include ${colourLabel(colour)}`" :disabled="disabled" />
						</td>
						<td :rowspan="rowSpan" class="finishing-table__colour">{{ colourLabel(colour) }}</td>
						<td v-if="payload.is_set_item" :rowspan="rowSpan">{{ rows[colour].part || "—" }}</td>
					</template>
					<td class="finishing-table__type">{{ reference.label }}</td>
					<td v-for="size in sizes" :key="size" class="erp-number">{{ formatQuantity(rows[colour].values?.[size]?.[reference.key] ?? 0) }}</td>
					<td class="erp-number finishing-table__row-total">{{ formatQuantity(referenceTotal(colour, reference.key)) }}</td>
				</tr>
				<tr class="finishing-entry-matrix__input-row">
					<template v-if="!references.length">
						<td class="finishing-table__index">
							<span>{{ index + 1 }}</span>
							<input v-if="checkable" v-model="modelValue[colour].checked" type="checkbox" class="finishing-entry-matrix__check" :aria-label="`Include ${colourLabel(colour)}`" :disabled="disabled" />
						</td>
						<td class="finishing-table__colour">{{ colourLabel(colour) }}</td>
						<td v-if="payload.is_set_item">{{ rows[colour].part || "—" }}</td>
					</template>
					<td class="finishing-table__type"><strong>{{ inputLabel }}</strong></td>
					<td v-for="size in sizes" :key="size" class="finishing-entry-matrix__cell">
						<input
							v-if="!checkable || modelValue[colour].checked"
							v-model="modelValue[colour].sizes[size]"
							type="number"
							min="0"
							step="any"
							inputmode="decimal"
							class="finishing-entry-input"
							:aria-label="`${colourLabel(colour)} ${size} ${inputLabel}`"
							:aria-invalid="invalid(modelValue[colour].sizes[size]) || undefined"
							:disabled="disabled"
						/>
						<span v-else class="finishing-entry-matrix__off">0</span>
					</td>
					<td class="erp-number finishing-table__row-total">{{ formatQuantity(inputTotal(colour)) }}</td>
				</tr>
			</tbody>
		</table>
	</div>
</template>

<script setup>
import { computed } from "vue"

import { colourLabel, formatQuantity } from "../finishingViews.js"

const props = defineProps({
	payload: { type: Object, required: true },
	modelValue: { type: Object, required: true },
	references: { type: Array, default: () => [] },
	inputLabel: { type: String, default: "Quantity" },
	checkable: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
})
const rows = computed(() => props.payload.data?.data || {})
const colours = computed(() => Object.keys(rows.value).filter((colour) => props.modelValue[colour]))
const sizes = computed(() => props.payload.primary_values || [])
const rowSpan = computed(() => props.references.length + 1)

function referenceTotal(colour, key) {
	return sizes.value.reduce((sum, size) => sum + (Number(rows.value[colour].values?.[size]?.[key]) || 0), 0)
}

function inputTotal(colour) {
	if (props.checkable && !props.modelValue[colour].checked) return 0
	return Object.values(props.modelValue[colour].sizes).reduce((sum, value) => sum + (Number(value) || 0), 0)
}

function invalid(value) {
	return value !== "" && value !== null && (!Number.isFinite(Number(value)) || Number(value) < 0)
}
</script>

<style scoped>
.finishing-entry-matrix__check { width: 16px; height: 16px; margin: 4px 0 0; accent-color: var(--erp-accent); }
.finishing-entry-matrix .finishing-table__index { white-space: nowrap; }
.finishing-entry-matrix .finishing-table__index span { display: block; }
.finishing-entry-matrix__input-row > td { background: color-mix(in srgb, var(--erp-accent-soft) 45%, var(--erp-surface)); }
.finishing-entry-matrix__cell { padding: 4px 6px !important; }
.finishing-entry-input[aria-invalid="true"] { border-color: var(--erp-danger); }
.finishing-entry-matrix__off { display: block; color: var(--erp-text-muted); text-align: right; }
</style>
