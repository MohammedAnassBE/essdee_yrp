<template>
	<section class="dependent-attribute-view" :aria-label="`${dependentAttribute} combination`">
		<h3>{{ dependentAttribute }} combination</h3>
		<div class="erp-table-wrap">
			<table class="erp-data-table dependent-attribute-table">
				<thead>
					<tr>
						<th scope="col">{{ dependentAttribute }}</th>
						<th scope="col">UOM<span v-if="editable" class="erp-required-mark" aria-hidden="true">*</span></th>
						<th scope="col">Display Name</th>
						<th v-for="attribute in attributes" :key="attribute" scope="col" class="dependent-attribute-table__check">{{ attribute }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.value">
						<th scope="row">
							{{ row.value }}
							<small v-for="problem in problems.filter((problem) => problem.stage === row.value && problem.field === 'stage_attributes')" :key="problem.message" class="stage-problem">{{ problem.message }}</small>
						</th>
						<td>
							<Select v-if="editable" v-model="row.uom" :options="uomOptions(row)" :aria-label="`${row.value} UOM`" fluid :invalid="!row.uom || problems.some((problem) => problem.stage === row.value && problem.field === 'uoms')" />
							<span v-else>{{ row.uom || "—" }}</span>
							<small v-for="problem in problems.filter((problem) => problem.stage === row.value && problem.field === 'uoms')" :key="problem.message" class="stage-problem">{{ problem.message }}</small>
						</td>
						<td>
							<InputText v-if="editable" v-model="row.display_name" :aria-label="`${row.value} Display Name`" fluid :invalid="problems.some((problem) => problem.stage === row.value && problem.field === 'dependent_details')" />
							<span v-else>{{ row.display_name || "—" }}</span>
							<small v-for="problem in problems.filter((problem) => problem.stage === row.value && problem.field === 'dependent_details')" :key="problem.message" class="stage-problem">{{ problem.message }}</small>
						</td>
						<td v-for="attribute in attributes" :key="attribute" class="dependent-attribute-table__check">
							<Checkbox v-if="editable" :model-value="row.attributes.includes(attribute)" binary :aria-label="`${row.value} uses ${attribute}`" @update:model-value="toggle(row, attribute, $event)" />
							<i v-else-if="row.attributes.includes(attribute)" class="pi pi-check" :aria-label="`${row.value} uses ${attribute}`" />
						</td>
					</tr>
				</tbody>
			</table>
		</div>
	</section>
</template>

<script setup>
import Checkbox from "primevue/checkbox"
import InputText from "primevue/inputtext"
import Select from "primevue/select"

const props = defineProps({
	dependentAttribute: { type: String, required: true },
	rows: { type: Array, default: () => [] },
	attributes: { type: Array, default: () => [] },
	editable: { type: Boolean, default: false },
	uoms: { type: Array, default: () => [] },
	problems: { type: Array, default: () => [] },
})

function uomOptions(row) {
	return [...new Set([...props.uoms.map((conversion) => conversion.uom).filter(Boolean), ...(row.uom ? [row.uom] : [])])]
}

function toggle(row, attribute, checked) {
	const others = row.attributes.filter((entry) => entry !== attribute)
	row.attributes = checked ? [...others, attribute] : others
}
</script>

<style scoped>
.dependent-attribute-view { display: grid; min-width: 0; gap: var(--erp-space-2); }
.stage-problem { display: block; max-width: 360px; color: var(--erp-danger-text, #b91c1c); white-space: normal; }
.dependent-attribute-view h3 { margin: 0; color: var(--erp-text); font-size: var(--erp-font-size-caption); }
.dependent-attribute-table tbody th { position: static; padding: var(--erp-table-cell-pad-y) var(--erp-table-cell-pad-x); color: var(--erp-text); font-size: var(--erp-font-size-table); font-weight: var(--erp-font-weight-semibold); letter-spacing: normal; text-align: left; text-transform: none; white-space: nowrap; background: transparent; border-bottom: 1px solid var(--erp-border-subtle); }
.dependent-attribute-table tbody tr:last-child > * { border-bottom: 0; }
.dependent-attribute-table td:nth-child(2) { min-width: 180px; }
.dependent-attribute-table td:nth-child(3) { min-width: 160px; }
.dependent-attribute-table .dependent-attribute-table__check { text-align: center; }
.dependent-attribute-table td.dependent-attribute-table__check i { color: var(--erp-success-text); font-weight: 700; }
</style>
