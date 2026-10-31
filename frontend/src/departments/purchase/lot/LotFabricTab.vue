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
												section.key === 'program' &&
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
							</tfoot>
						</table>
					</div>
				</section>
				<section v-if="entry.ledger.length" class="lot-group">
					<header class="lot-group__header">
						<strong>Process Ledger</strong>
						<span>{{ countLabel(entry.ledger.length, "step") }}</span>
					</header>
					<div class="lot-section__body">
						<section
							v-for="step in entry.ledger"
							:key="step.process_name"
							class="lot-group"
						>
							<header class="lot-group__header">
								<strong><DocumentLink doctype="YRP Process" :name="step.process_name" /></strong>
								<span>{{ step.shape }}</span>
							</header>
							<template v-for="side in ['outputs', 'inputs']" :key="side">
								<template v-if="step[side].length">
									<header class="lot-group__header">
										<strong>
											{{ side === "inputs" ? "Input" : "Output" }}
										</strong>
										<span>{{ countLabel(step[side].length, "row") }}</span>
									</header>
									<div
										class="erp-table-wrap lot-table-wrap"
										role="region"
										tabindex="0"
										:aria-label="`${step.process_name} ${side}`"
									>
										<table class="erp-data-table lot-table">
											<thead>
												<tr>
													<th>Dia</th>
													<th>Colour</th>
													<th class="erp-number">Planned</th>
													<th class="erp-number">Received</th>
													<th class="erp-number">Balance</th>
												</tr>
											</thead>
											<tbody>
												<tr
													v-for="(row, rowIndex) in step[side]"
													:key="rowIndex"
												>
													<td>{{ row.dia || "—" }}</td>
													<td>{{ row.colour || "—" }}</td>
													<td class="erp-number">
														{{ formatQuantity(row.planned) }}
													</td>
													<td class="erp-number">
														{{ formatQuantity(row.received) }}
													</td>
													<td
														class="erp-number"
														:class="balanceClass(row.balance)"
													>
														{{ formatQuantity(row.balance) }}
													</td>
												</tr>
											</tbody>
										</table>
									</div>
								</template>
							</template>
						</section>
					</div>
				</section>
				<section class="lot-group">
					<header class="lot-group__header">
						<strong>Actual Dia Conversions</strong>
						<span>{{ conversions(entry, index).changed }} changed · {{ conversions(entry, index).routes }} routes</span>
						<label class="lot-conversion-toggle">
							<Checkbox
								v-model="includeUnchanged[index]"
								binary
								:input-id="`lot-conversions-${index}`"
							/>
							Include unchanged routes
						</label>
					</header>
					<div class="lot-conversion-controls">
						<InputText v-model="conversionSearch[index]" placeholder="Search conversions" aria-label="Search Actual Dia conversions" />
						<Select v-model="conversionProcess[index]" :options="[{ label: 'All', value: '' }, ...conversionProcesses(entry.conversions).map((name) => ({ label: name, value: name }))]" option-label="label" option-value="value" placeholder="All processes" aria-label="Conversion process" />
						<span>{{ conversions(entry, index).rows.length }} shown</span>
					</div>
					<div
						v-if="conversions(entry, index).rows.length"
						class="erp-table-wrap lot-table-wrap"
						role="region"
						tabindex="0"
						aria-label="Actual Dia conversions"
					>
						<table class="erp-data-table lot-table">
							<thead>
								<tr>
									<th>Process</th>
									<th>Planned Item → Actual Item</th>
									<th class="erp-number">Quantity</th>
									<th>Source</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="(row, rowIndex) in conversions(entry, index).rows"
									:key="rowIndex"
								>
									<td><DocumentLink doctype="YRP Process" :name="row.process_name" /></td>
									<td><DocumentLink doctype="Item" :name="row.planned_item" /> → <DocumentLink doctype="Item" :name="row.actual_item" /></td>
									<td class="erp-number">
										{{ formatQuantity(row.actual_quantity) }}
										{{ row.stock_uom }}
									</td>
									<td>{{ countLabel(row.source_grn_count || 0, "GRN") }}<br /><DocumentLink v-if="row.production_detail" doctype="YRP Item Production Detail" :name="row.production_detail" /></td>
								</tr>
							</tbody>
						</table>
					</div>
					<LotEmptyState
						v-else
						:title="entry.conversions?.length ? 'No matching routes' : 'No Actual Dia conversions'"
						:reason="entry.conversions?.length ? 'Adjust the search, process or Include unchanged routes filter.' : 'Conversions appear after submitting Default Knitting GRNs.'"
					/>
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
					v-if="
						!entry.matrices.length &&
						!entry.ledger.length &&
						!entry.conversions?.length &&
						!entry.legacy.length
					"
					title="No cloth program"
					reason="No program or movement is recorded for this route."
				/>
			</div>
		</section>
	</div>
</template>

<script setup>
import { programDia, programColour } from "../../../engine/lotClothProgram.js"
import Button from "primevue/button"
import ClothProgramDialog from "./ClothProgramDialog.vue"
import InputText from "primevue/inputtext"
import Select from "primevue/select"
import Checkbox from "primevue/checkbox"
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
	stepSections,
	conversionProcesses,
	conversionView,
	weightMatrix,
} from "./lotViews.js"

const props = defineProps({
	lot: { type: String, default: "" },
	modified: { type: String, default: "" },
	canWrite: { type: Boolean, default: false },
	fabrics: { type: Array, default: () => [] },
	otherConversions: { type: Array, default: () => [] },
})
const emit = defineEmits(["changed"])
const builderOpen = ref(false)
const includeUnchanged = ref({})
const conversionSearch = ref({})
const conversionProcess = ref({})
function conversions(entry, index) { return conversionView(entry.conversions, { search: conversionSearch.value[index], process: conversionProcess.value[index], includeUnchanged: includeUnchanged.value[index] }) }
const cards = computed(() => {
	const entries = [...props.fabrics]
	if (props.otherConversions.length) entries.push({ conversions: props.otherConversions })
	return entries.map((entry) => ({
		...entry,
		badge: planBadge(entry),
		matrices: fabricMatrices(entry),
		ledger: stepSections(entry.steps || []),
		legacy: legacyRows(entry.legacy_colour_program || []),
	}))
})

function fabricMatrices(entry) {
	return [
		{
			key: "program",
			label: "Knitting Program (Dia × Colour, Kg)",
			rows: entry.program || [],
			options: {
				dia: programDia,
				colour: programColour,
			},
		},
	]
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

function balanceClass(value) {
	return value < 0 ? "lot-negative" : value > 0 ? "lot-positive" : ""
}
</script>

<style scoped>
.lot-conversion-controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; padding: 12px; }
</style>
