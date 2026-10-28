<template>
	<IpdSection :section-key="sectionKey">
		<template v-if="!readonly" #actions>
			<Button label="Generate combinations" icon="pi pi-th-large" text severity="secondary" size="small" @click="openGenerate" />
			<Button label="Add row" icon="pi pi-plus" text severity="secondary" size="small" @click="compacting.add({ colour: null, input_dia: null, compacting_dia: null, notes: null })" />
		</template>
		<div class="ipd-cloth-stack">
			<p class="erp-help-text">Colour/Dia compacting data only. Leave Colour blank for an all-colours mapping; excluded from every calculation and Work Order.</p>
			<EntryGrid
				v-if="compacting.rows.value.length"
				ref="compactingGrid" validation-field="compacting_reference_details"
				:rows="compacting.keys.value"
				:columns="columns"
				:model-value="compacting.model.value"
				:readonly="readonly"
				:errors="compacting.errors.value"
				title="Compacting Details"
				meta="Blank colour applies to all colours"
				aria-label="Compacting references"
				row-header-label="#"
				:toolbar="['fillDown', 'paste', 'clear']"
				:removable-rows="!readonly"
				@update:model-value="compacting.update"
				@remove-row="compacting.remove"
				:add-row="readonly ? null : () => compacting.add({ colour: null, input_dia: null, compacting_dia: null, notes: null })"
				settings-doctype="YRP Item Production Detail" settings-child-doctype="SD YRP IPD Compacting Reference"
			>
				<template v-if="!readonly" #toolbar>
					<Button label="Fill compacting dia" icon="pi pi-pencil" text severity="secondary" size="small" @click="openFill" />
				</template>
			</EntryGrid>
			<p v-else class="erp-empty-state erp-empty-state--compact ipd-cloth-empty">No compacting references. Generate them from the fabric routes or add rows.</p>
			<p v-if="notice.text" class="ipd-cloth-strip" :class="`ipd-cloth-strip--${notice.tone}`" role="status">
				<i :class="notice.tone === 'error' ? 'pi pi-exclamation-circle' : 'pi pi-info-circle'" aria-hidden="true" />
				{{ notice.text }}
			</p>
		</div>

		<Dialog v-model:visible="generateOpen" modal class="erp-entity-dialog erp-dialog--md" header="Generate compacting combinations">
			<div class="ipd-cloth-dialog__body">
				<div class="ipd-cloth-dialog__field">
					<label class="erp-field-label" for="ipd-compacting-scope">Generation scope</label>
					<Select v-model="scope" input-id="ipd-compacting-scope" :options="COMPACTING_SCOPES" fluid />
				</div>
				<fieldset v-if="scope === 'Colour Group'" class="ipd-cloth-dialog__choices">
					<legend class="erp-field-label">Colour group</legend>
					<label v-for="colour in colours" :key="colour"><Checkbox v-model="groupColours" :value="colour" />{{ colour }}</label>
				</fieldset>
				<p class="erp-help-text">Only missing combinations are added. Existing compacting dias are never overwritten.</p>
				<Message v-if="dialogError" severity="error" :closable="false">{{ dialogError }}</Message>
			</div>
			<template #footer>
				<Button label="Cancel" severity="secondary" text @click="generateOpen = false" />
				<Button label="Generate combinations" icon="pi pi-th-large" @click="generate" />
			</template>
		</Dialog>

		<Dialog v-model:visible="fillOpen" modal class="erp-entity-dialog erp-dialog--md" header="Fill compacting dia">
			<div class="ipd-cloth-dialog__body">
				<div class="ipd-cloth-dialog__field">
					<label class="erp-field-label" for="ipd-compacting-input-dia">Knitting/Input dia</label>
					<Select v-model="fillInputDia" input-id="ipd-compacting-input-dia" :options="inputDias" fluid @change="selectRowsFor(fillInputDia)" />
				</div>
				<fieldset v-if="fillInputDia" class="ipd-cloth-dialog__choices">
					<legend class="erp-field-label">Rows</legend>
					<label v-for="row in rowsForInputDia" :key="row.key"><Checkbox v-model="fillKeys" :value="row.key" />{{ row.label }}</label>
				</fieldset>
				<div class="ipd-cloth-dialog__field">
					<label class="erp-field-label" for="ipd-compacting-dia">Compacting dia<span class="erp-required-mark" aria-hidden="true">*</span></label>
					<Select v-model="fillDia" input-id="ipd-compacting-dia" :options="dias" filter fluid />
				</div>
				<Message v-if="dialogError" severity="error" :closable="false">{{ dialogError }}</Message>
			</div>
			<template #footer>
				<Button label="Cancel" severity="secondary" text @click="fillOpen = false" />
				<Button label="Fill selected rows" icon="pi pi-check" @click="fill" />
			</template>
		</Dialog>
	</IpdSection>
</template>

<script setup>
import { computed, ref } from "vue"
import Button from "primevue/button"
import Checkbox from "primevue/checkbox"
import Dialog from "primevue/dialog"
import Message from "primevue/message"
import Select from "primevue/select"

import EntryGrid from "../../../../components/common/EntryGrid.vue"
import IpdSection from "../IpdSection.vue"
import {
	COMPACTING_SCOPES,
	addCompactingTargets,
	compactingInputDias,
	compactingRoutePairs,
	compactingTargets,
	fillCompactingDia,
	pairColours,
	rowKey,
	withStoredOptions,
} from "./clothGrids.js"
import { useClothSection, useClothTable, useGridFocus } from "./useClothTable.js"
import "./cloth.css"

const props = defineProps({
	sectionKey: { type: String, required: true },
	readonly: { type: Boolean, default: false },
})

const FIELDS = ["colour", "input_dia", "compacting_dia", "notes"]

const { editor, readonly, cloth } = useClothSection(props)
const compacting = useClothTable(editor, "compacting_reference_details", FIELDS)
const compactingGrid = ref(null)
const colourOptions = computed(() => withStoredOptions(cloth.value.colour_values || [], compacting.rows.value, ["colour"]))
const dias = computed(() => withStoredOptions(cloth.value.dia_values || [], compacting.rows.value, ["input_dia", "compacting_dia"]))
const columns = computed(() => [
	{ key: "colour", label: "Colour (Blank = All Colours)", type: "value", options: colourOptions.value },
	{ key: "input_dia", label: "Knitting/Input Dia", type: "value", options: dias.value },
	{ key: "compacting_dia", label: "Compacting Dia", type: "value", options: dias.value },
	{ key: "notes", label: "Notes", type: "text" },
])

const notice = ref({ text: "", tone: "info" })
const dialogError = ref("")
const generateOpen = ref(false)
const scope = ref(COMPACTING_SCOPES[0])
const groupColours = ref([])
const pairs = computed(() => compactingRoutePairs(editor.draft, { colourAttribute: cloth.value.colour_attribute, diaAttribute: cloth.value.dia_attribute }))
const colours = computed(() => pairColours(pairs.value))

function openGenerate() {
	notice.value = { text: "", tone: "info" }
	if (!pairs.value.length) {
		notice.value = { text: "Add fabric routes or fabric process colour and dia changes first, then generate compacting combinations.", tone: "error" }
		return
	}
	dialogError.value = ""
	groupColours.value = []
	generateOpen.value = true
}

function generate() {
	if (scope.value === "Colour Group" && !groupColours.value.length) {
		dialogError.value = "Select at least one colour for the group."
		return
	}
	const result = addCompactingTargets(compacting.rows.value, compactingTargets(pairs.value, scope.value, groupColours.value))
	if (result.added) editor.setValue("compacting_reference_details", result.rows)
	notice.value = {
		text: result.added ? `${result.added} compacting combination${result.added === 1 ? "" : "s"} added. Enter the compacting dia.` : "Every combination in this scope is already present.",
		tone: "info",
	}
	generateOpen.value = false
}

const fillOpen = ref(false)
const fillInputDia = ref(null)
const fillKeys = ref([])
const fillDia = ref(null)
const inputDias = computed(() => compactingInputDias(compacting.rows.value))
const rowsForInputDia = computed(() => compacting.rows.value
	.map((row, index) => ({ row, key: rowKey(row, index), label: row.colour || "All colours" }))
	.filter((entry) => entry.row.input_dia === fillInputDia.value))

function selectRowsFor(inputDia) {
	fillKeys.value = rowsForInputDia.value.filter((entry) => entry.row.input_dia === inputDia).map((entry) => entry.key)
}

function openFill() {
	dialogError.value = ""
	fillInputDia.value = inputDias.value.length === 1 ? inputDias.value[0] : null
	fillDia.value = null
	selectRowsFor(fillInputDia.value)
	fillOpen.value = true
}

function fill() {
	const result = fillCompactingDia(compacting.rows.value, fillKeys.value, fillDia.value)
	if (result.error) {
		dialogError.value = result.error
		return
	}
	editor.setValue("compacting_reference_details", result.rows)
	notice.value = { text: `${result.updated} row${result.updated === 1 ? "" : "s"} updated.`, tone: "info" }
	fillOpen.value = false
}

useGridFocus(editor, props.sectionKey, {
	compacting_reference_details: { grid: compactingGrid, firstRow: () => compacting.keys.value[0]?.key, firstColumn: "compacting_dia" },
})
</script>
