<template>
	<div class="lot-tab-stack">
		<Button v-if="lot && canWrite" label="Build Cloth Program" icon="pi pi-cog" @click="buildOpen = true" />
		<ClothProgramBuildDialog v-if="lot" v-model:visible="buildOpen" :lot="lot" :modified="modified" @saved="emit('changed')" @setup="openSetup" />
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
								<tr v-if="section.kind === 'program' && hasAddWeight(entry, section)" class="lot-add-weight">
									<th>Add Weight</th>
									<td
										v-for="colour in section.matrix.colours"
										:key="colour"
										class="erp-number"
									>
										{{ signedKg(drafts[addWeightKey(entry.cloth_item, section.fabricType, colour)]) }}
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
	</div>
</template>

<script setup>
import { addWeightDrafts, addWeightKey, programDia, programColour, programFabricTypes } from "../../../engine/lotClothProgram.js"
import Button from "primevue/button"
import ClothProgramBuildDialog from "./ClothProgramBuildDialog.vue"
import ClothProgramDialog from "./ClothProgramDialog.vue"
import Message from "primevue/message"
import Tag from "primevue/tag"
import { computed, ref } from "vue"
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
const buildOpen = ref(false)
const builderOpen = ref(false)
const drafts = computed(() => addWeightDrafts(props.fabrics))

function openSetup() {
	buildOpen.value = false
	builderOpen.value = true
}

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
