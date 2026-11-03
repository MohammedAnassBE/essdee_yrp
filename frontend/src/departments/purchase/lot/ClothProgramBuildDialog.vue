<template>
	<Dialog
		:visible="visible"
		modal
		header="Build Cloth Program"
		:style="{ width: 'min(1100px, calc(100vw - 32px))' }"
		@update:visible="close"
		@show="calculate(true)"
	>
		<div class="cpb">
			<label class="cpb-excess">
				<strong>Cloth Excess Percentage</strong>
				<InputNumber v-model="excessPercentage" input-id="cpb-excess" :min="0" :min-fraction-digits="0" :max-fraction-digits="3" suffix="%" />
				<small class="lot-muted">Adds this percentage to every calculated cloth Colour and Dia.</small>
			</label>
			<Message v-if="error" severity="error" :closable="false">{{ error }}</Message>
			<div v-if="!preview" class="lot-muted">{{ busy ? "Calculating cloth program…" : "Enter the Cloth Excess Percentage and click Calculate." }}</div>
			<template v-else>
				<small class="lot-muted">
					Nothing is saved until you click Save or Print. Edit Add Weight (Kg, negative reduces) and click Calculate.
					Cloth Kg per 1 Kg Yarn: <strong>{{ preview.cloth_per_kg_yarn }}</strong> · Extra: <strong>{{ preview.extra_percentage }}%</strong>
				</small>
				<section v-for="table in preview.tables" :key="table.cloth_item" class="lot-group">
					<header class="lot-group__header">
						<strong>{{ table.cloth_item }}</strong>
						<span>Knitting Program Kg</span>
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
											:use-grouping="false"
											:max-fraction-digits="0"
											:aria-label="`Add Weight ${group.fabric_type} ${colour}`"
											placeholder="0"
											input-class="lot-add-weight__input"
										/>
									</td>
									<td class="erp-number lot-total">{{ signedKg(group.additional_total) }}</td>
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
				<div class="cpb-totals">
					<span>Required Kg: <strong>{{ kg(preview.display_totals.required_weight) }}</strong></span>
					<span>Extra Kg: <strong>{{ kg(preview.display_totals.extra_weight) }}</strong></span>
					<span>Added Kg: <strong>{{ signedKg(preview.display_totals.manual_additional_weight) }}</strong></span>
					<span>Total Knitting Program Kg: <strong>{{ kg(preview.display_totals.program_weight) }}</strong></span>
				</div>
			</template>
		</div>
		<template #footer>
			<Button label="Setup" icon="pi pi-cog" severity="secondary" text :disabled="busy" @click="emit('setup')" />
			<Button label="Calculate" icon="pi pi-calculator" severity="secondary" :loading="busy === 'calculate'" :disabled="Boolean(busy)" @click="calculate(false)" />
			<Button label="Print" icon="pi pi-print" severity="secondary" :loading="busy === 'print'" :disabled="Boolean(busy) || !preview" @click="print" />
			<Button label="Save" icon="pi pi-check" :loading="busy === 'save'" :disabled="Boolean(busy) || !preview" @click="save('save')" />
		</template>
	</Dialog>
</template>

<script setup>
import { ref } from "vue"
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
const emit = defineEmits(["update:visible", "saved", "setup"])
const excessPercentage = ref(0)
const preview = ref(null)
const drafts = ref({})
const busy = ref("")
const error = ref("")

const kg = (value) => formatQuantity(Math.round(Number(value) || 0))
const signedKg = (value) => (Number(value) > 0 ? `+${kg(value)}` : Number(value) ? kg(value) : "—")

function close(nextVisible) {
	if (!nextVisible && busy.value) return
	emit("update:visible", nextVisible)
}

function inputs() {
	return { lot: props.lot, excess_percentage: excessPercentage.value || 0, additions: JSON.stringify(previewAdditions(preview.value, drafts.value)) }
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

async function calculate(opening) {
	if (opening) preview.value = null
	const args = opening ? { lot: props.lot } : inputs()
	const result = await run("calculate", () => callMethod("essdee_yrp.api.cloth_program.get_cloth_program_preview", args))
	if (!result) return
	preview.value = result
	excessPercentage.value = result.extra_percentage
	drafts.value = previewAddWeightDrafts(result)
}

async function save(action) {
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
.cpb-totals { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 18px; }
.lot-add-weight :deep(.lot-add-weight__input) { width: 100%; min-width: 64px; text-align: right; }
</style>
