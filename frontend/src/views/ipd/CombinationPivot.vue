<!--
  CombinationPivot — the checkbox-driven combination view shared by the Cutting
  and Cloth Accessory tabs (Desk CuttingItemDetail / ClothAccessory widgets +
  the MultiCheck attribute selector).

  The user ticks attributes → "Build" regenerates the grid on the server → the
  pivot renders one column per attribute: checked attributes are display-only,
  Dia picks Dia values, Weight/Required GSM are numbers, Cloth selects from the
  cloth list, anything else picks from the packing mapping. A header input per
  editable column fills the whole column (Desk "Fill"). Never a raw child grid.
  Desk parity: toggling a checkbox clears + regenerates the combination.
-->
<template>
	<div class="cp-block">
		<div class="cp-head">
			<span class="cp-title">{{ title }}</span>
			<!-- Desk hides the combination button when its prerequisites are
			     missing (e.g. no cloth details) — buildDisabled mirrors that. -->
			<Button
				v-if="editing && !buildDisabled"
				size="small"
				text
				:label="'Build'"
				:loading="building"
				:data-testid="testId + '-build'"
				@click="$emit('build', {})"
			/>
		</div>

		<!-- Attribute checkboxes -->
		<div class="cp-checks" :data-testid="testId + '-checks'">
			<label v-for="opt in options" :key="opt" class="cp-check">
				<input
					type="checkbox"
					:checked="checked.includes(opt)"
					:disabled="!editing"
					@change="toggle(opt, $event.target.checked)"
				/>
				<span>{{ opt }}</span>
			</label>
			<span v-if="!options.length" class="cp-empty">No attributes available</span>
		</div>

		<!-- Grid -->
		<div v-if="grid && (grid.items || []).length" class="cp-scroll">
			<table class="cp-table" :data-testid="testId + '-grid'">
				<thead>
					<tr>
						<th v-for="col in grid.attributes" :key="col">
							<div>{{ col === "Weight" ? "Weight (Kg)" : col }}</div>
							<!-- Fill-down input for editable columns (Desk "Fill") -->
							<div v-if="editing && kind(col) !== 'ro'" class="cp-fill">
								<input
									v-if="kind(col) === 'float' || kind(col) === 'int'"
									v-model.number="fillValues[col]"
									type="number"
									:step="kind(col) === 'int' ? 1 : 'any'"
									class="cp-num"
								/>
								<Select
									v-else-if="kind(col) === 'select'"
									v-model="fillValues[col]"
									:options="selectOptions"
									size="small"
									class="cp-select"
								/>
								<!-- Link cells commit on SELECT only — free-typed text never
								     lands in the JSON (no server validation behind it). -->
								<LinkField
									v-else
									:model-value="fillValues[col] || ''"
									target-doctype="Item Attribute Value"
									:search-handler="searchFor(col)"
									class="cp-link"
									@item-select="(e) => (fillValues[col] = e.value)"
								/>
								<button class="cp-fillbtn" type="button" @click="fillColumn(col)">Fill</button>
							</div>
						</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, ri) in grid.items" :key="ri">
						<td v-for="col in grid.attributes" :key="col">
							<template v-if="!editing || kind(col) === 'ro'">
								<span>{{ row[col] ?? "—" }}</span>
							</template>
							<input
								v-else-if="kind(col) === 'float' || kind(col) === 'int'"
								v-model.number="row[col]"
								type="number"
								:step="kind(col) === 'int' ? 1 : 'any'"
								class="cp-num"
								@change="kind(col) === 'int' && (row[col] = row[col] ? Math.trunc(Number(row[col])) : null)"
							/>
							<Select
								v-else-if="kind(col) === 'select'"
								v-model="row[col]"
								:options="selectOptions"
								size="small"
								class="cp-select"
							/>
							<!-- Commit on SELECT only (see header note). -->
							<LinkField
								v-else
								:model-value="row[col] || ''"
								target-doctype="Item Attribute Value"
								:search-handler="searchFor(col)"
								class="cp-link"
								@item-select="(e) => (row[col] = e.value)"
							/>
						</td>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else class="cp-empty">No combination yet</div>
	</div>
</template>

<script setup>
import { reactive, watch } from "vue";
import Button from "primevue/button";
import Select from "primevue/select";
import LinkField from "@/components/LinkField.vue";
import { cellKind, diaSearch, CELL } from "./combinationCells";

const props = defineProps({
	title: { type: String, required: true },
	testId: { type: String, required: true },
	editing: { type: Boolean, default: false },
	options: { type: Array, default: () => [] },
	checked: { type: Array, default: () => [] },
	grid: { type: Object, default: null },
	readOnlyColumns: { type: Array, default: () => [] },
	mappingSearch: { type: Function, required: true },
	selectOptions: { type: Array, default: () => [] },
	building: { type: Boolean, default: false },
	buildDisabled: { type: Boolean, default: false },
});
const emit = defineEmits(["update:checked", "build"]);

const fillValues = reactive({});
// A rebuilt grid has new columns/rows — stale fill drafts must not survive it.
watch(
	() => props.grid,
	() => {
		Object.keys(fillValues).forEach((k) => delete fillValues[k]);
	},
);

const kind = (col) => cellKind(col, props.readOnlyColumns);
const searchFor = (col) => (kind(col) === CELL.LINK_DIA ? diaSearch : props.mappingSearch);

function toggle(opt, on) {
	const next = on ? [...props.checked, opt] : props.checked.filter((c) => c !== opt);
	emit("update:checked", next);
	// Desk MultiCheck on_change parity: the combination resets + regenerates.
	// fromToggle lets the consumer keep the untick-all deliberate-clear SILENT
	// (no "tick the attributes" error for an intentional clear).
	emit("build", { fromToggle: true });
}

function fillColumn(col) {
	const v = fillValues[col];
	if (v === undefined || v === null || v === "") return;
	(props.grid?.items || []).forEach((row) => {
		row[col] = v;
	});
}
</script>

<!-- Styling comes from the shared ipd-sections.css (one design across tabs). -->
