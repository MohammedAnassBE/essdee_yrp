<template>
	<div class="lot-tab-stack">
		<template v-if="itemDetails">
			<Button
				v-if="!composerOpen"
				label="Add row"
				icon="pi pi-plus"
				severity="secondary"
				outlined
				:disabled="disabled"
				@click="emit('update:composerOpen', true)"
			/>
			<section
				v-else
				class="lot-group lot-order-composer"
				aria-label="Add box quantity row"
				@keydown.enter="addOnLastEnter"
			>
				<header class="lot-group__header">
					<strong>Add row</strong>
				</header>
				<div class="lot-section__body">
					<div class="lot-composer-attributes">
						<div
							v-for="attribute in itemDetails.final_state_attr"
							:key="attribute"
						>
							<label :for="`lot-row-${attribute}`">{{ attribute }}</label>
							<LinkField
								doctype="Item Attribute Value"
								v-model="entry.attributes[attribute]"
								:input-id="`lot-row-${attribute}`"
								:aria-label="attribute"
								:search-handler="attributeSearch(attribute)"
								:show-open-button="false"
								:disabled="disabled"
							/>
							<small
								v-if="attempted && !entry.attributes[attribute]"
								class="merch-field-error"
							>
								{{ attribute }} is required.
							</small>
						</div>
					</div>
					<div
						v-if="itemDetails.primary_attribute"
						class="erp-table-wrap lot-table-wrap"
						role="region"
						tabindex="0"
						aria-label="New box quantities"
					>
						<table v-entry-table class="erp-data-table lot-table">
							<thead>
								<tr>
									<th>Details</th>
									<th
										v-for="size in itemDetails.primary_attribute_values"
										:key="size"
										class="erp-number"
									>
										{{ size }} {{ itemDetails.default_uom }}
									</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="stage in stages"
									:key="stage.key"
								>
									<td class="lot-stage-label">
										<span>{{ stage.label }}</span>
									</td>
									<td
										v-for="size in itemDetails.primary_attribute_values"
										:key="size"
										class="erp-number"
									>
										<InputNumber
											v-model="entry.values[size][stage.key]"
											:aria-label="`${stage.label} ${size} ${itemDetails.default_uom}`"
											:invalid="
												Boolean(
													boxCellError(
														stage.key,
														entry.values[size][stage.key],
													),
												)
											"
											:max-fraction-digits="3"
											:disabled="disabled"
											fluid
										/>
										<small
											v-if="
												boxCellError(
													stage.key,
													entry.values[size][stage.key],
												)
											"
											class="merch-field-error"
										>
											{{
												boxCellError(
													stage.key,
													entry.values[size][stage.key],
												)
											}}
										</small>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
					<div
						v-else
						class="lot-composer-values"
					>
						<div
							v-for="stage in stages"
							:key="stage.key"
						>
							<label :for="`lot-row-${stage.key}`">
								{{ stage.label
								}}{{ stage.key === "qty" ? ` ${itemDetails.default_uom}` : "" }}
							</label>
							<InputNumber
								v-model="entry.values[stage.key]"
								:input-id="`lot-row-${stage.key}`"
								:aria-label="stage.label"
								:invalid="Boolean(boxCellError(stage.key, entry.values[stage.key]))"
								:max-fraction-digits="3"
								:disabled="disabled"
								fluid
							/>
							<small
								v-if="boxCellError(stage.key, entry.values[stage.key])"
								class="merch-field-error"
							>
								{{ boxCellError(stage.key, entry.values[stage.key]) }}
							</small>
						</div>
					</div>
					<small
						v-if="attempted && !hasQuantity"
						class="merch-field-error"
					>
						Fill the quantity.
					</small>
					<Button
						label="Add row"
						icon="pi pi-plus"
						:disabled="disabled"
						@click="addRow"
					/>
				</div>
			</section>
		</template>
		<DocumentErrorDialog
			:message="error"
			@dismiss="error = ''"
		/>
	</div>
</template>
<script setup>
import Button from "primevue/button"
import InputNumber from "primevue/inputnumber"
import { computed, ref, watch } from "vue"
import { callMethod } from "../../../api/frappe.js"
import LinkField from "../../../components/common/LinkField.vue"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"
import { vEntryTable } from "../../../components/common/childGrid/entryTable.js"
import { addLotOrderRow, lotOrderEntry } from "../../purchase/lot/lotEditor.js"
import { boxCellError, boxGridErrors } from "./merchLotViews.js"
const props = defineProps({
	itemDetails: { type: Object, default: null },
	composerOpen: Boolean,
	disabled: Boolean,
})
const emit = defineEmits(["update:itemDetails", "update:composerOpen"])
const entry = ref(null)
const error = ref("")
const attempted = ref(false)
const hasQuantity = computed(() =>
	props.itemDetails.primary_attribute
		? Object.values(entry.value.values).some((cell) => Number(cell.qty) > 0)
		: Number(entry.value.values.qty) > 0,
)
const stages = [
	{ key: "qty", label: "Qty" },
	{ key: "ratio", label: "Ratio" },
	{ key: "mrp", label: "MRP" },
]
watch(
	() => props.itemDetails,
	(details) => {
		entry.value = details ? lotOrderEntry(details) : null
	},
	{ immediate: true },
)
function attributeSearch(attribute) {
	return async (text) =>
		(
			await callMethod("yrp.yrp.doctype.yrp_item.yrp_item.search_item_attribute_values", {
				txt: text,
				attribute,
				item: props.itemDetails.item,
			})
		).map((value) => ({ name: value, label: value }))
}
function addRow() {
	attempted.value = true
	if (Object.keys(boxGridErrors({ ...props.itemDetails, items: [entry.value] })).length) return
	if (
		!hasQuantity.value ||
		props.itemDetails.final_state_attr.some((attribute) => !entry.value.attributes[attribute])
	)
		return
	try {
		emit("update:itemDetails", addLotOrderRow(props.itemDetails, entry.value))
		emit("update:composerOpen", false)
		error.value = ""
		attempted.value = false
	} catch (reason) {
		error.value = reason.message
	}
}
/** Enter on the composer's last input adds the row, like clicking Add row. */
function addOnLastEnter(event) {
	if (event.shiftKey || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
	const inputs = event.currentTarget.querySelectorAll("input:not([type=hidden]):not(:disabled)")
	if (event.target !== inputs[inputs.length - 1]) return
	event.preventDefault()
	addRow()
}
</script>
