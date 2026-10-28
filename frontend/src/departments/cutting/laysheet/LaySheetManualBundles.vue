<template>
	<section class="data-block editable-data-block manual-bundles">
		<header>
			<div class="data-block__title"><h3>Bundle Details</h3><span>{{ rows.length }} rows<template v-if="dirty"> · unsaved changes</template></span></div>
			<div v-if="editable" class="manual-bundles__actions">
				<Button label="Add Row" icon="pi pi-plus" size="small" severity="secondary" outlined :disabled="busy" @click="addRow" />
				<Button v-if="dirty" label="Discard" size="small" severity="secondary" text :disabled="busy" @click="reset" />
				<Button label="Save Bundles" icon="pi pi-check" size="small" :disabled="!dirty" :loading="busy" @click="save" />
			</div>
		</header>
		<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
		<div v-if="rows.length" class="table-scroll" role="region" tabindex="0" aria-label="Manual bundle details">
			<table class="laysheet-table manual-bundles__table">
				<thead>
					<tr>
						<th>S.No</th><th>Colour</th><th>Major Colour</th><th v-if="isSetItem">Set Colour</th><th>Shade</th><th>Quantity</th>
						<th v-for="size in sizes" :key="size" class="manual-bundles__number">{{ size }}</th>
						<th v-if="editable" aria-label="Actions"></th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, index) in rows" :key="row.key">
						<td>{{ index + 1 }}</td>
						<template v-if="editable">
							<td><Select v-model="row.colour" :options="colours" filter fluid :aria-label="`Colour for bundle row ${index + 1}`" @change="colourChanged(row)" /></td>
							<td><Select v-model="row.major_colour" :options="colours" filter fluid :aria-label="`Major colour for bundle row ${index + 1}`" @change="touch" /></td>
							<td v-if="isSetItem"><Select v-model="row.set_colour" :options="colours" filter fluid :aria-label="`Set colour for bundle row ${index + 1}`" @change="touch" /></td>
							<td><InputText v-model="row.shade" fluid :aria-label="`Shade for bundle row ${index + 1}`" @input="touch" /></td>
							<td><InputNumber v-model="row.quantity" :min="1" :use-grouping="false" fluid :aria-label="`Quantity for bundle row ${index + 1}`" @input="touch" /></td>
							<td v-for="size in sizes" :key="size"><InputNumber v-model="row.multipliers[size]" :min="0" :use-grouping="false" fluid :aria-label="`${size} multiplier for bundle row ${index + 1}`" @input="touch" /></td>
							<td><Button icon="pi pi-trash" severity="danger" text rounded :aria-label="`Delete bundle row ${index + 1}`" :disabled="busy" @click="removeRow(index)" /></td>
						</template>
						<template v-else>
							<td>{{ row.colour }}</td><td>{{ row.major_colour }}</td><td v-if="isSetItem">{{ row.set_colour }}</td><td>{{ row.shade }}</td><td>{{ row.quantity }}</td>
							<td v-for="size in sizes" :key="size" class="manual-bundles__number">{{ row.multipliers[size] }}</td>
						</template>
					</tr>
				</tbody>
			</table>
		</div>
		<div v-else class="empty-data">No bundle details yet.</div>
	</section>
</template>

<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import Select from "primevue/select"
import { computed, ref, watch } from "vue"

import { applySetFieldDefaults, emptyManualRow, manualRowsFromSheet, manualRowsPayload, validateManualRows } from "./manualBundles.js"

const props = defineProps({
	sheet: { type: Object, required: true },
	colours: { type: Array, default: () => [] },
	editable: Boolean,
	busy: Boolean,
	loadSetFields: { type: Function, required: true },
})
const emit = defineEmits(["save"])

const rows = ref([])
const dirty = ref(false)
const error = ref("")
let rowKey = 0
const sizes = computed(() => props.sheet.sizes || [])
const isSetItem = computed(() => Boolean(props.sheet.is_set_item))

watch(() => [props.sheet.name, props.sheet.modified], reset, { immediate: true })

function reset() {
	rows.value = manualRowsFromSheet(props.sheet).map(keyed)
	dirty.value = false
	error.value = ""
}

function keyed(row) {
	return { ...row, key: ++rowKey }
}

function touch() {
	dirty.value = true
	error.value = ""
}

function addRow() {
	rows.value.push(keyed(emptyManualRow(sizes.value)))
	touch()
}

function removeRow(index) {
	rows.value.splice(index, 1)
	touch()
}

async function colourChanged(row) {
	touch()
	if (!row.colour) return
	try {
		applySetFieldDefaults(row, await props.loadSetFields(row.colour), isSetItem.value)
	} catch (reason) {
		error.value = reason.message || "Unable to load the colour's set details."
	}
}

function save() {
	const options = { sizes: sizes.value, isSetItem: isSetItem.value }
	error.value = validateManualRows(rows.value, options)
	if (!error.value) emit("save", manualRowsPayload(rows.value, options))
}
</script>

<style scoped>
.manual-bundles__actions { display: flex; align-items: center; gap: 6px; }
.manual-bundles__table td { vertical-align: middle; }
.manual-bundles__table td :deep(.p-select), .manual-bundles__table td :deep(.p-inputtext) { min-width: 6rem; }
.manual-bundles__table td :deep(.p-inputnumber-input) { min-width: 4.5rem; text-align: right; }
.manual-bundles__number { text-align: right; }
</style>
