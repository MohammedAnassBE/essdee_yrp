<template>
	<div class="lot-tab-stack">
		<Button v-if="lot && canWrite" label="Build Cloth Program" icon="pi pi-cog" @click="builderOpen = true" />
		<ClothProgramDialog v-if="lot" v-model:visible="builderOpen" :lot="lot" :modified="modified" @built="emit('changed')" />
		<section
			v-for="(entry, index) in cards"
			:key="entry.cloth_item || index"
			class="lot-section"
		>
			<header>
				<div>
					<span>Cloth route</span>
					<h2><DocumentLink doctype="Item" :name="entry.cloth_item" :label="entry.cloth_item || 'Unassigned cloth route'" /></h2>
					<small v-if="entry.production_detail" class="lot-muted">
						<DocumentLink doctype="YRP Item Production Detail" :name="entry.production_detail" />
					</small>
				</div>
				<Tag
					v-if="entry.badge"
					:value="entry.badge.text"
					:severity="entry.badge.severity"
				/>
			</header>
			<div class="lot-section__body">
				<Message v-if="entry.plan_error" severity="error" :closable="false">
					{{ entry.plan_error }}
				</Message>
				<section v-for="section in entry.matrices" :key="section.key" class="lot-group">
					<header class="lot-group__header">
						<strong>{{ section.label }}</strong>
						<span>{{ countLabel(section.matrix.dias.length, "row") }}</span>
					</header>
					<div
						class="erp-table-wrap lot-table-wrap"
						role="region"
						tabindex="0"
						:aria-label="section.label"
					>
						<table class="erp-data-table lot-table lot-table--compact">
							<thead>
								<tr>
									<th>Dia</th>
									<th
										v-for="colour in section.matrix.colours"
										:key="colour"
										class="erp-number"
									>
										{{ colour || "Program" }}
										<Tag
											v-if="
												section.kind === 'program' &&
												entry.dyed_yarn_colours?.includes(colour)
											"
											value="Dyed Yarn"
											severity="info"
										/>
									</th>
									<th class="erp-number">Total</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="dia in section.matrix.dias" :key="dia">
									<td>{{ dia }}</td>
									<td
										v-for="colour in section.matrix.colours"
										:key="colour"
										class="erp-number"
									>
										{{ formatQuantity(section.matrix.cells[dia][colour]) }}
									</td>
									<td class="erp-number lot-total">
										{{ quantityTotal(section.matrix.diaTotals[dia]) }}
									</td>
								</tr>
							</tbody>
							<tfoot>
								<tr>
									<th>Total</th>
									<td
										v-for="colour in section.matrix.colours"
										:key="colour"
										class="erp-number"
									>
										{{ quantityTotal(section.matrix.colourTotals[colour]) }}
									</td>
									<td class="erp-number lot-total">
										{{ quantityTotal(section.matrix.total) }}
									</td>
								</tr>
								<tr v-if="section.kind === 'program' && (editable || hasAddWeight(entry, section))" class="lot-add-weight">
									<th>Add Weight</th>
									<td
										v-for="colour in section.matrix.colours"
										:key="colour"
										class="erp-number"
									>
										<InputNumber
											v-if="editable"
											v-model="drafts[addWeightKey(entry.cloth_item, section.fabricType, colour)]"
											:use-grouping="false"
											:max-fraction-digits="0"
											:aria-label="`Add Weight ${section.fabricType} ${colour}`"
											placeholder="0"
											input-class="lot-add-weight__input"
										/>
										<span v-else>{{ signedKg(drafts[addWeightKey(entry.cloth_item, section.fabricType, colour)]) }}</span>
									</td>
									<td class="erp-number lot-total">{{ signedKg(addWeightTotal(entry, section)) }}</td>
								</tr>
							</tfoot>
						</table>
					</div>
				</section>
				<section v-if="entry.legacy.length" class="lot-group">
					<header class="lot-group__header">
						<strong>Legacy Colour Program</strong>
						<span>{{ countLabel(entry.legacy.length, "row") }}</span>
					</header>
					<div
						class="erp-table-wrap lot-table-wrap"
						role="region"
						tabindex="0"
						aria-label="Legacy colour program"
					>
						<table class="erp-data-table lot-table">
							<thead>
								<tr>
									<th>Dia</th>
									<th>Colour</th>
									<th class="erp-number">Weight</th>
									<th class="erp-number">Received</th>
									<th class="erp-number">Compacted</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="(row, rowIndex) in entry.legacy" :key="rowIndex">
									<td>{{ row.dia }}</td>
									<td>{{ row.colour }}</td>
									<td class="erp-number">{{ formatQuantity(row.weight) }}</td>
									<td class="erp-number">
										{{ formatQuantity(row.received_weight) }}
									</td>
									<td class="erp-number">
										{{ formatQuantity(row.compacted_weight) }}
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
				<LotEmptyState
					v-if="!entry.matrices.length && !entry.legacy.length"
					title="No cloth program"
					reason="No knitting program is recorded for this route."
				/>
			</div>
		</section>
		<div v-if="editable && cards.length" class="lot-add-weight__actions">
			<small class="lot-muted">
				The percentage and added weights are saved on this Lot; click Calculate again after editing Add Weight. Negative Kg reduces that colour.
			</small>
			<Button label="Calculate" icon="pi pi-calculator" :loading="calculating" @click="calculate" />
		</div>
	</div>
</template>

<script setup>
import { addWeightDrafts, addWeightKey, programDia, programColour, programFabricTypes, serializeAddWeight } from "../../../engine/lotClothProgram.js"
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import { useToast } from "primevue/usetoast"
import { callMethod } from "../../../api/frappe.js"
import ClothProgramDialog from "./ClothProgramDialog.vue"
import Message from "primevue/message"
import Tag from "primevue/tag"
import { computed, ref, watch } from "vue"
import DocumentLink from "../../../components/common/DocumentLink.vue"

import LotEmptyState from "./LotEmptyState.vue"
import {
	countLabel,
	formatQuantity,
	planBadge,
	quantityTotal,
	weightMatrix,
} from "./lotViews.js"

const props = defineProps({
	lot: { type: String, default: "" },
	modified: { type: String, default: "" },
	canWrite: { type: Boolean, default: false },
	fabrics: { type: Array, default: () => [] },
})
const emit = defineEmits(["changed"])
const builderOpen = ref(false)
const toast = useToast()
const editable = computed(() => Boolean(props.lot && props.canWrite))
const drafts = ref({})
const calculating = ref(false)
watch(() => props.fabrics, (fabrics) => { drafts.value = addWeightDrafts(fabrics) }, { immediate: true })

function hasAddWeight(entry, section) {
	return section.matrix.colours.some((colour) => Number(drafts.value[addWeightKey(entry.cloth_item, section.fabricType, colour)]))
}

function addWeightTotal(entry, section) {
	return section.matrix.colours.reduce(
		(sum, colour) => sum + (Number(drafts.value[addWeightKey(entry.cloth_item, section.fabricType, colour)]) || 0), 0)
}

function signedKg(value) {
	const kg = Number(value) || 0
	return kg > 0 ? `+${kg}` : kg ? String(kg) : "—"
}

async function calculate() {
	calculating.value = true
	try {
		await callMethod("essdee_yrp.api.cloth_program.recalculate_cloth_program", {
			lot: props.lot,
			modified: props.modified,
			additions: JSON.stringify(serializeAddWeight(props.fabrics, drafts.value)),
		})
		emit("changed")
	} catch (error) {
		toast.add({ severity: "error", summary: "Calculate failed", detail: error.message })
	} finally {
		calculating.value = false
	}
}
const cards = computed(() => {
	return props.fabrics.map((entry) => ({
		...entry,
		badge: planBadge(entry),
		matrices: fabricMatrices(entry),
		legacy: legacyRows(entry.legacy_colour_program || []),
	}))
})

function fabricMatrices(entry) {
	const fabricTypes = programFabricTypes({ program: entry.program || [] })
	return fabricTypes
		.map(({ fabricType, rows }) => ({
			key: `program:${fabricType}`,
			kind: "program",
			fabricType,
			label: fabricTypes.length > 1 ? `${fabricType} · Knitting Program (Dia × Colour, Kg)` : "Knitting Program (Dia × Colour, Kg)",
			rows,
			options: {
				dia: programDia,
				colour: programColour,
			},
		}))
		.filter((section) => section.rows.length)
		.map((section) => ({ ...section, matrix: weightMatrix(section.rows, section.options) }))
}

function legacyRows(rows) {
	const matrix = weightMatrix(rows)
	const received = weightMatrix(rows, { weight: "received_weight" })
	const compacted = weightMatrix(rows, { weight: "compacted_weight" })
	return matrix.dias.flatMap((dia) =>
		matrix.colours
			.filter((colour) =>
				rows.some((row) => row.dia === dia && (row.colour || "") === colour),
			)
			.map((colour) => ({
				dia,
				colour,
				weight: matrix.cells[dia][colour],
				received_weight: received.cells[dia][colour],
				compacted_weight: compacted.cells[dia][colour],
			})),
	)
}
</script>

<style scoped>
.lot-add-weight__actions {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	gap: 12px;
	flex-wrap: wrap;
}
.lot-add-weight :deep(.lot-add-weight__input) {
	width: 100%;
	min-width: 64px;
	text-align: right;
}
</style>
