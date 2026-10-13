<template>
	<div class="lotwise-workspace__layout">
		<div class="lotwise-workspace__sections">
			<section class="lotwise-section erp-card">
				<header><span>01</span><h2>Details</h2></header>
				<div class="lotwise-section__field-grid">
					<FormField
						v-for="fieldname in LOTWISE_SECTIONS.header"
						:key="fieldname"
						:field="fieldByName(fieldname)"
						:model-value="form[fieldname]"
						:form="form"
						:disabled="fieldsDisabled"
						:required="Boolean(fieldByName(fieldname).reqd)"
						@update:model-value="emit('update-field', fieldname, $event)"
					/>
				</div>
			</section>

			<section class="lotwise-section erp-card">
				<header><span>02</span><h2>Qty and Rate</h2></header>
				<ChildTableField
					:field="fieldByName('qty_rate_chart')"
					:model-value="form.qty_rate_chart || []"
					:child-meta="childMetaFor('qty_rate_chart')"
					:disabled="fieldsDisabled"
					@update:model-value="emit('update-table', 'qty_rate_chart', $event)"
				/>
				<div class="lotwise-section__inline-action">
					<FormField
						:field="fieldByName('additional_rate')"
						:model-value="form.additional_rate"
						:form="form"
						:disabled="fieldsDisabled"
						@update:model-value="emit('update-field', 'additional_rate', $event)"
					/>
					<Button
						v-if="canEdit"
						label="Add Rate"
						icon="pi pi-plus"
						severity="secondary"
						outlined
						:loading="activeCommand === 'add_rate'"
						:disabled="pageBusy"
						@click="emit('command', 'add_rate')"
					/>
				</div>
			</section>

			<section class="lotwise-section erp-card">
				<header><span>03</span><h2>Cloth Value</h2></header>
				<ChildTableField
					:field="fieldByName('cloth_value')"
					:model-value="form.cloth_value || []"
					:child-meta="childMetaFor('cloth_value')"
					:disabled="fieldsDisabled"
					@update:model-value="emit('update-table', 'cloth_value', $event)"
				/>
				<div v-if="canEdit" class="lotwise-section__button-row">
					<Button
						label="Get Size × Cloth Combination"
						icon="pi pi-th-large"
						severity="secondary"
						outlined
						:loading="activeCommand === 'build_piece_cloth_weight'"
						:disabled="pageBusy"
						@click="emit('command', 'build_piece_cloth_weight')"
					/>
					<Button
						label="Calculate Cloth Qty"
						icon="pi pi-calculator"
						severity="secondary"
						outlined
						:loading="activeCommand === 'calculate_cloth_qty'"
						:disabled="pageBusy"
						@click="emit('command', 'calculate_cloth_qty')"
					/>
				</div>
				<ChildTableField
					:field="fieldByName('piece_cloth_weight')"
					:model-value="form.piece_cloth_weight || []"
					:child-meta="childMetaFor('piece_cloth_weight')"
					:disabled="fieldsDisabled"
					@update:model-value="emit('update-table', 'piece_cloth_weight', $event)"
				/>
			</section>

			<section class="lotwise-section erp-card">
				<header><span>04</span><h2>Production Cost</h2></header>
				<div class="lotwise-section__inline-action">
					<FormField
						:field="fieldByName('production_cost_template')"
						:model-value="form.production_cost_template"
						:form="form"
						:disabled="fieldsDisabled"
						@update:model-value="emit('update-field', 'production_cost_template', $event)"
					/>
					<Button
						v-if="canEdit"
						label="Set Template"
						icon="pi pi-copy"
						severity="secondary"
						outlined
						:loading="activeCommand === 'apply_production_cost_template'"
						:disabled="pageBusy || !form.production_cost_template"
						@click="emit('command', 'apply_production_cost_template')"
					/>
				</div>
				<ChildTableField
					v-for="table in ['cmt', 'packing_materials', 'trims']"
					:key="table"
					:field="fieldByName(table)"
					:model-value="form[table] || []"
					:child-meta="childMetaFor(table)"
					:disabled="fieldsDisabled"
					@update:model-value="emit('update-table', table, $event)"
				/>
			</section>

			<section v-for="section in additionalCostSections" :key="section.key" class="lotwise-section erp-card">
				<header><span>{{ section.number }}</span><h2>{{ section.label }}</h2></header>
				<div class="lotwise-section__inline-action">
					<FormField
						:field="fieldByName(section.template)"
						:model-value="form[section.template]"
						:form="form"
						:disabled="fieldsDisabled"
						@update:model-value="emit('update-field', section.template, $event)"
					/>
					<Button
						v-if="canEdit"
						label="Set Template"
						icon="pi pi-copy"
						severity="secondary"
						outlined
						:loading="activeCommand === section.command"
						:disabled="pageBusy || !form[section.template]"
						@click="emit('command', section.command)"
					/>
				</div>
				<ChildTableField
					:field="fieldByName(section.table)"
					:model-value="form[section.table] || []"
					:child-meta="childMetaFor(section.table)"
					:disabled="fieldsDisabled"
					@update:model-value="emit('update-table', section.table, $event)"
				/>
			</section>

			<section class="lotwise-section erp-card">
				<header><span>07</span><h2>GST</h2></header>
				<div class="lotwise-section__single-field">
					<FormField
						:field="fieldByName('gst')"
						:model-value="form.gst"
						:form="form"
						:disabled="fieldsDisabled"
						@update:model-value="emit('update-field', 'gst', $event)"
					/>
				</div>
			</section>
		</div>

		<LotwiseTotalsRail :values="form" />
	</div>
</template>

<script setup>
import Button from "primevue/button"

import ChildTableField from "../../../components/common/ChildTableField.vue"
import FormField from "../../../components/common/FormField.vue"
import { LOTWISE_SECTIONS, lotwiseChildMeta } from "../pdViews.js"
import LotwiseTotalsRail from "./LotwiseTotalsRail.vue"

const props = defineProps({
	form: { type: Object, required: true },
	fields: { type: Object, required: true },
	metadataByName: { type: Object, required: true },
	fieldsDisabled: { type: Boolean, default: false },
	canEdit: { type: Boolean, default: false },
	pageBusy: { type: Boolean, default: false },
	activeCommand: { type: String, default: "" },
})
const emit = defineEmits(["update-field", "update-table", "command"])

const additionalCostSections = [
	{ key: "trade", number: "05", label: "Trade Discounts", template: "trade_discounts_template", table: "trade_discounts", command: "apply_discount_template" },
	{ key: "other", number: "06", label: "Other Costs", template: "other_costs_template", table: "other_costs", command: "apply_other_cost_template" },
]

function fieldByName(fieldname) {
	return props.fields[fieldname]
}

function childMetaFor(fieldname) {
	return lotwiseChildMeta(fieldname, props.metadataByName[fieldByName(fieldname).options])
}
</script>

<style scoped>
.lotwise-workspace__sections, .lotwise-section { display: grid; min-width: 0; gap: var(--erp-space-3); }
.lotwise-workspace__layout { display: grid; min-width: 0; grid-template-columns: minmax(0, 1fr) minmax(300px, 380px); align-items: start; gap: var(--erp-space-3); }
.lotwise-section { padding: var(--erp-space-4); border-color: var(--erp-border); }
.lotwise-section > header { display: flex; align-items: center; gap: 9px; padding-bottom: 9px; border-bottom: 1px solid var(--erp-border-subtle); }
.lotwise-section > header span { color: var(--erp-accent-hover); font-size: var(--erp-font-size-min); font-weight: 780; }
.lotwise-section h2 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-section); }
.lotwise-section__field-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-items: start; gap: var(--erp-space-3); }
.lotwise-section__inline-action, .lotwise-section__button-row { display: flex; align-items: end; gap: 8px; flex-wrap: wrap; }
.lotwise-section__inline-action > :first-child { min-width: min(100%, 320px); flex: 1 1 260px; }
.lotwise-section__single-field { max-width: 320px; }
@media (max-width: 1120px) { .lotwise-workspace__layout { grid-template-columns: 1fr; } }
@media (max-width: 820px) { .lotwise-section__field-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .lotwise-section__button-row { align-items: stretch; flex-direction: column; } .lotwise-section__button-row > * { width: 100%; } .lotwise-section { padding: var(--erp-space-3); } .lotwise-section__field-grid { grid-template-columns: 1fr; } }
</style>
