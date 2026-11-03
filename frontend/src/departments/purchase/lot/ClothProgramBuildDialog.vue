<template>
	<Dialog
		:visible="visible"
		modal
		header="Build Cloth Program"
		:style="{ width: 'min(1100px, calc(100vw - 32px))' }"
		@update:visible="close"
		@show="open"
	>
		<div class="cpb">
			<label class="cpb-excess">
				<strong>Cloth Excess Percentage</strong>
				<InputNumber v-model="excessPercentage" input-id="cpb-excess" @input="typedExcess = $event.value" :min="0" :min-fraction-digits="0" :max-fraction-digits="3" suffix="%" />
				<small class="lot-muted">Adds this percentage to every calculated cloth Colour and Dia.</small>
			</label>
			<Message v-if="previewError || error" severity="error" :closable="false">{{ previewError || error }}</Message>
			<div v-if="!preview" class="lot-muted">{{ busy || updating ? "Calculating cloth program…" : "" }}</div>
			<template v-else>
				<small class="lot-muted">
					Nothing is saved until you click Save or Print. Add Weight is Kg, negative reduces; totals update as you type.
					Cloth Kg per 1 Kg Yarn: <strong>{{ preview.cloth_per_kg_yarn }}</strong> · Extra: <strong>{{ preview.extra_percentage }}%</strong>
				</small>
				<section v-for="table in preview.tables" :key="table.cloth_item" class="lot-group">
					<header class="lot-group__header">
						<strong>{{ table.cloth_item }}</strong>
						<span>Knitting Program Kg<small v-if="updating" class="lot-muted cpb-updating"> · Updating…</small></span>
					</header>
					<div class="erp-table-wrap lot-table-wrap" role="region" tabindex="0" :aria-label="`${table.cloth_item} Knitting Program Kg`">
						<table class="erp-data-table lot-table lot-table--compact">
							<thead>
								<tr>
									<th>Fabric Type</th>
									<th>Dia</th>
									<th v-for="colour in table.colours" :key="colour" class="erp-number">{{ colour }}</th>
									<th class="erp-number">Total</th>
								</tr>
							</thead>
							<tbody v-for="group in table.fabric_groups" :key="group.fabric_type">
								<tr v-for="route in group.routes" :key="route.dia">
									<td>{{ route.fabric_type }}</td>
									<td>{{ route.dia }}</td>
									<td v-for="colour in table.colours" :key="colour" class="erp-number">{{ route.weights[colour] ? kg(route.weights[colour]) : "—" }}</td>
									<td class="erp-number lot-total">{{ kg(route.total) }}</td>
								</tr>
								<tr class="cpb-subtotal">
									<th colspan="2">Total {{ group.fabric_type }}</th>
									<th v-for="colour in table.colours" :key="colour" class="erp-number">{{ kg(group.colour_totals[colour]) }}</th>
									<th class="erp-number">{{ kg(group.total) }}</th>
								</tr>
								<tr class="lot-add-weight">
									<th colspan="2">Add Weight</th>
									<td v-for="colour in table.colours" :key="colour" class="erp-number">
										<InputNumber
											v-model="drafts[addWeightKey(table.cloth_item, group.fabric_type, colour)]"
											@input="typed[addWeightKey(table.cloth_item, group.fabric_type, colour)] = $event.value"
											:use-grouping="false"
											:max-fraction-digits="0"
											:aria-label="`Add Weight ${group.fabric_type} ${colour}`"
											placeholder="0"
											input-class="lot-add-weight__input"
										/>
									</td>
									<td class="erp-number lot-total">{{ signedKg(addWeightTotal(table, group)) }}</td>
								</tr>
							</tbody>
							<tfoot>
								<tr>
									<th colspan="2">Total</th>
									<th v-for="colour in table.colours" :key="colour" class="erp-number">{{ kg(table.colour_totals[colour]) }}</th>
									<th class="erp-number lot-total">{{ kg(table.total) }}</th>
								</tr>
							</tfoot>
						</table>
					</div>
				</section>
				<div class="cpb-totals" :class="{ 'cpb-stale': updating }">
					<span>Required Kg: <strong>{{ kg(preview.display_totals.required_weight) }}</strong></span>
					<span>Extra Kg: <strong>{{ kg(preview.display_totals.extra_weight) }}</strong></span>
					<span>Added Kg: <strong>{{ signedKg(preview.display_totals.manual_additional_weight) }}</strong></span>
					<span>Total Knitting Program Kg: <strong>{{ kg(preview.display_totals.program_weight) }}</strong></span>
				</div>
			</template>
		</div>
		<template #footer>
			<Button label="Print" icon="pi pi-print" severity="secondary" :loading="busy === 'print'" :disabled="!canStore" @click="print" />
			<Button label="Save" icon="pi pi-check" :loading="busy === 'save'" :disabled="!canStore" @click="save('save')" />
		</template>
	</Dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import Message from "primevue/message"
import { callMethod } from "../../../api/frappe.js"
import { addWeightKey, previewAdditions, previewAddWeightDrafts } from "../../../engine/lotClothProgram.js"
import { buildPrintUrl } from "../../../utils/printUrl.js"
import { formatQuantity } from "./lotViews.js"

const props = defineProps({
	visible: { type: Boolean, default: false },
	lot: { type: String, required: true },
	modified: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "saved"])
const excessPercentage = ref(0)
const preview = ref(null)
const drafts = ref({})
// InputNumber commits v-model on blur; keystrokes land here so the preview stays live.
const typed = ref({})
const typedExcess = ref(undefined)
const busy = ref("")
const error = ref("")
const updating = ref(false)
const previewError = ref("")
const canStore = computed(() => !busy.value && Boolean(preview.value) && !previewError.value)
const PREVIEW_DELAY = 350
let previewTimer = null
let previewRequest = 0
let previewPending = null
let requestedInputs = ""

const kg = (value) => formatQuantity(Math.round(Number(value) || 0))
const signedKg = (value) => (Number(value) > 0 ? `+${kg(value)}` : Number(value) ? kg(value) : "—")

function close(nextVisible) {
	if (!nextVisible && busy.value) return
	emit("update:visible", nextVisible)
}

function inputs() {
	const excess = typedExcess.value === undefined ? excessPercentage.value : typedExcess.value
	const additions = previewAdditions(preview.value, { ...drafts.value, ...typed.value })
	return { lot: props.lot, excess_percentage: excess || 0, additions: JSON.stringify(additions) }
}

async function run(action, request) {
	busy.value = action
	error.value = ""
	try {
		return await request()
	} catch (failure) {
		error.value = failure.message
		return null
	} finally {
		busy.value = ""
	}
}

const addWeightTotal = (table, group) =>
	table.colours.reduce((total, colour) => {
		const key = addWeightKey(table.cloth_item, group.fabric_type, colour)
		return total + (Number(key in typed.value ? typed.value[key] : drafts.value[key]) || 0)
	}, 0)

async function open() {
	clearTimeout(previewTimer)
	previewRequest += 1
	preview.value = null
	previewError.value = ""
	updating.value = false
	const result = await run("calculate", () => callMethod("essdee_yrp.api.cloth_program.get_cloth_program_preview", { lot: props.lot }))
	if (!result) return
	preview.value = result
	excessPercentage.value = result.extra_percentage
	drafts.value = Object.fromEntries(Object.entries(previewAddWeightDrafts(result)).map(([key, weight]) => [key, weight || null]))
	typed.value = {}
	typedExcess.value = undefined
	requestedInputs = JSON.stringify(inputs())
}

// Live preview: the latest inputs win; older responses are dropped.
function refreshPreview() {
	clearTimeout(previewTimer)
	previewTimer = null
	const request = ++previewRequest
	const args = inputs()
	requestedInputs = JSON.stringify(args)
	updating.value = true
	previewPending = callMethod("essdee_yrp.api.cloth_program.get_cloth_program_preview", args).then(
		(result) => {
			if (request !== previewRequest) return
			preview.value = result
			previewError.value = ""
		},
		(failure) => {
			if (request === previewRequest) previewError.value = failure.message
		},
	).finally(() => {
		if (request === previewRequest) updating.value = false
	})
	return previewPending
}

watch(
	() => preview.value && JSON.stringify(inputs()),
	(current) => {
		if (!current || current === requestedInputs) return
		clearTimeout(previewTimer)
		previewTimer = setTimeout(refreshPreview, PREVIEW_DELAY)
	},
	{ deep: true },
)

async function currentPreviewIsValid() {
	if (previewTimer) await refreshPreview()
	else if (updating.value) await previewPending
	return !previewError.value
}

async function save(action) {
	if (!(await currentPreviewIsValid())) return false
	const saved = await run(action, () =>
		callMethod("essdee_yrp.api.cloth_program.recalculate_cloth_program", { ...inputs(), modified: props.modified }).then(() => true),
	)
	if (!saved) return false
	emit("saved")
	if (action === "save") emit("update:visible", false)
	return true
}

async function print() {
	const printWindow = window.open("", "_blank")
	if (!(await save("print"))) {
		printWindow?.close()
		return
	}
	const url = buildPrintUrl({ doctype: "SD YRP Lot", name: props.lot, format: "Essdee Lot Cloth Program", noLetterhead: true })
	if (printWindow) printWindow.location.href = url
	else error.value = "Saved. Please enable pop-ups to print."
}
</script>

<style scoped>
.cpb { display: flex; flex-direction: column; gap: 14px; }
.cpb-excess { display: flex; flex-direction: column; gap: 6px; max-width: 360px; }
.cpb-subtotal th { font-weight: 600; }
.cpb-stale { opacity: 0.6; }
.cpb-updating { font-weight: 400; }
.cpb-totals { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 18px; }
.lot-add-weight :deep(.lot-add-weight__input) { width: 100%; min-width: 64px; text-align: right; }
</style>
