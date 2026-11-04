<template>
	<Dialog
		:visible="visible"
		header="Build Cloth Programs"
		modal
		class="merch-cloth-dialog"
		:style="{ width: '760px', maxWidth: 'calc(100vw - 24px)' }"
		@update:visible="emit('update:visible', $event)"
	>
		<p
			v-if="loading"
			role="status"
		>
			Loading demanded cloths…
		</p>
		<div
			v-else
			class="lot-tab-stack"
		>
			<div class="merch-cloth-field">
				<label for="merch-cloth-excess">Cloth Excess Percentage</label>
				<InputNumber
					v-model="excess"
					input-id="merch-cloth-excess"
					:disabled="acting"
					:max-fraction-digits="3"
					fluid
				/>
				<small
					v-if="attempted && excess < 0"
					class="merch-field-error"
				>
					Cloth Excess Percentage cannot be negative.
				</small>
			</div>
			<p v-if="!selections.length">No cloth demand. Run Calculate Order Items first.</p>
			<section
				v-for="(selection, index) in selections"
				:key="selection.cloth_item"
				class="lot-section"
			>
				<header>
					<h2>{{ selection.label }} · {{ selection.cloth_item }}</h2>
				</header>
				<div class="lot-section__body lot-tab-stack">
					<div>
						Item Yarn Recipe:
						{{
							selection.item_yarns
								.map((row) => `${row.yarn_item} ${row.ratio}%`)
								.join(" + ") || "—"
						}}
						<small
							v-if="errors[index]?.item_yarns"
							class="merch-field-error"
						>
							{{ errors[index].item_yarns }}
						</small>
					</div>
					<div class="erp-table-wrap">
						<table class="erp-data-table">
							<thead>
								<tr>
									<th>Finished Colour</th>
									<th>Is Dyed Yarn</th>
									<th>Same Finished Colour</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="colour in selection.required_colours"
									:key="colour"
								>
									<td>{{ colour }}</td>
									<td>
										<input
											type="checkbox"
											:aria-label="`Is Dyed Yarn ${colour}`"
											:checked="selection.dyed_yarn_colours.includes(colour)"
											:disabled="acting"
											@change="
												setDyed(selection, colour, $event.target.checked)
											"
										/>
									</td>
									<td>
										<input
											type="checkbox"
											:aria-label="`Same Finished Colour ${colour}`"
											:checked="
												selection.same_finished_colours.includes(colour)
											"
											:disabled="
												acting ||
												selection.dyed_yarn_colours.includes(colour)
											"
											@change="
												setColour(
													selection.same_finished_colours,
													colour,
													$event.target.checked,
												)
											"
										/>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
					<div class="merch-cloth-field">
						<label :for="`cloth-ratio-${index}`">Cloth Kgs / 1 Kg Yarn *</label>
						<InputNumber
							v-model="selection.cloth_per_kg_yarn"
							:input-id="`cloth-ratio-${index}`"
							:disabled="acting"
							:max-fraction-digits="4"
							fluid
						/>
						<small
							v-if="errors[index]?.cloth_per_kg_yarn"
							class="merch-field-error"
						>
							{{ errors[index].cloth_per_kg_yarn }}
						</small>
					</div>
					<div
						v-for="field in processFields"
						:key="field.key"
						class="merch-cloth-field"
					>
						<label :for="`${field.key}-${index}`">{{ field.label }}</label>
						<LinkField
							v-model="selection[field.key]"
							doctype="YRP Process"
							:input-id="`${field.key}-${index}`"
							:show-open-button="false"
							:disabled="acting"
						/>
						<small
							v-if="errors[index]?.[field.key]"
							class="merch-field-error"
						>
							{{ errors[index][field.key] }}
						</small>
					</div>
					<small
						v-if="errors[index]?.routes"
						class="merch-field-error"
					>
						{{ errors[index].routes }}
					</small>
				</div>
			</section>
		</div>
		<template #footer>
			<small
				v-if="blockedMessage"
				class="merch-field-error"
				role="alert"
			>
				{{ blockedMessage }}
			</small>
			<Button
				label="Cancel"
				severity="secondary"
				text
				:disabled="acting"
				@click="emit('update:visible', false)"
			/>
			<Button
				label="Build"
				:loading="acting"
				:disabled="loading || !selections.length || acting"
				@click="build"
			/>
		</template>
	</Dialog>
</template>
<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputNumber from "primevue/inputnumber"
import { computed, ref, watch } from "vue"
import { getMerchClothProgramContext, getMerchYarnProfile } from "../../../api/merch.js"
import LinkField from "../../../components/common/LinkField.vue"
import { buildBlockMessage, buildSelection, clothErrors, clothSelection, contextExcessPercentage } from "./clothProgram.js"
const props = defineProps({
	visible: Boolean,
	lotId: { type: String, required: true },
	excessPercentage: { type: Number, default: 0 },
	acting: Boolean,
})
const emit = defineEmits(["update:visible", "build", "error"])
const loading = ref(false)
const attempted = ref(false)
const blockedMessage = ref("")
const excess = ref(0)
const selections = ref([])
const errors = computed(() =>
	selections.value.map((selection) =>
		attempted.value
			? clothErrors(selection)
			: clothErrors(selection).item_yarns
				? { item_yarns: clothErrors(selection).item_yarns }
				: {},
	),
)
const processFields = [
	{ key: "knitting_process", label: "Knitting Process *" },
	{ key: "dyeing_process", label: "Dyeing Process" },
]
let sequence = 0
async function loadSelections() {
	const context = await getMerchClothProgramContext(props.lotId)
	const cloths = await Promise.all(
		context.cloths.map(async (cloth) => {
			if (!cloth.profile?.knitting_process && cloth.item_yarns?.[0]?.yarn_item) {
				cloth.profile = {
					...cloth.profile,
					...(await getMerchYarnProfile(cloth.item_yarns[0].yarn_item)),
				}
			}
			return clothSelection(cloth, context.defaults)
		}),
	)
	return { cloths, excess: contextExcessPercentage(context, props.excessPercentage) }
}
watch(
	() => props.visible,
	async (visible) => {
		const request = ++sequence
		if (!visible) return
		loading.value = true
		attempted.value = false
		blockedMessage.value = ""
		selections.value = []
		excess.value = props.excessPercentage
		try {
			const loaded = await loadSelections()
			if (request === sequence) {
				selections.value = loaded.cloths
				excess.value = loaded.excess
			}
		} catch (error) {
			if (request === sequence) {
				emit("update:visible", false)
				emit("error", error.message)
			}
		} finally {
			if (request === sequence) loading.value = false
		}
	},
)
function setColour(colours, colour, checked) {
	const index = colours.indexOf(colour)
	if (checked && index < 0) colours.push(colour)
	if (!checked && index >= 0) colours.splice(index, 1)
}
function setDyed(selection, colour, checked) {
	setColour(selection.dyed_yarn_colours, colour, checked)
	if (checked) setColour(selection.same_finished_colours, colour, false)
}
function build() {
	attempted.value = true
	blockedMessage.value = buildBlockMessage(selections.value, excess.value)
	if (blockedMessage.value) return
	emit("build", {
		selections: selections.value.map(buildSelection),
		excess_percentage: excess.value || 0,
	})
}
</script>
