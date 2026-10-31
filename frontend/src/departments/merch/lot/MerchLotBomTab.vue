<template>
	<div class="lot-tab-stack">
		<LotBomTab :bom="{ ...(bom || {}), additional: [] }" />
		<section class="lot-section">
			<div class="lot-section__body lot-tab-stack">
				<ChildTableField
					parent-doctype="SD YRP Lot"
					v-if="metadata"
					v-model="rows"
					:field="{
						fieldname: 'bom_additional_items',
						label: 'BOM Additional Items',
						options: 'SD YRP Lot BOM',
					}"
					:child-meta="metadata"
					:disabled="!canEdit || acting"
					:errors="errors"
				/>
				<Button
					v-if="canEdit"
					label="Save BOM Additional Items"
					icon="pi pi-save"
					:disabled="acting"
					:loading="acting"
					@click="save"
				/>
			</div>
		</section>
	</div>
</template>
<script setup>
import Button from "primevue/button"
import { computed, onMounted, ref, watch } from "vue"
import { getMeta } from "../../../api/frappe.js"
import ChildTableField from "../../../components/common/ChildTableField.vue"
import LotBomTab from "../../purchase/lot/LotBomTab.vue"
const props = defineProps({
	bom: { type: Object, default: null },
	additionalItems: { type: Array, default: () => [] },
	canEdit: Boolean,
	acting: Boolean,
})
const emit = defineEmits(["save", "error"])
const metadata = ref(null)
const rows = ref([])
const attempted = ref(false)
const fields = ["item_name", "process_name", "uom", "required_qty"]
watch(
	() => props.additionalItems,
	(value) => {
		rows.value = JSON.parse(JSON.stringify(value))
		attempted.value = false
	},
	{ immediate: true },
)
const errors = computed(() =>
	!attempted.value
		? {}
		: Object.fromEntries(
				rows.value.flatMap((row, index) =>
					fields
						.filter((field) => !row[field])
						.map((field) => [
							`${index}.${field}`,
							`${metadata.value?.fields.find((column) => column.fieldname === field)?.label || field} is required.`,
						]),
				),
			),
)
onMounted(async () => {
	try {
		metadata.value = (await getMeta("SD YRP Lot BOM")).find(
			(document) => document.name === "SD YRP Lot BOM",
		)
	} catch (error) {
		emit("error", error.message)
	}
})
function save() {
	attempted.value = true
	if (!Object.keys(errors.value).length) emit("save", { rows: rows.value })
}
</script>
