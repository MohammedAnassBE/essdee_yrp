<template>
	<Dialog
		:visible="visible"
		modal
		header="Create Colour"
		class="erp-dialog--md"
		:closable="!busy"
		:dismissable-mask="false"
		@update:visible="setVisible"
	>
		<form id="product-colour-create" class="product-colour-create" @submit.prevent="save">
			<label class="product-colour-create__field">
				<span>Colour <strong>*</strong></span>
				<InputText v-model="colour" fluid :disabled="busy" autofocus />
			</label>
			<div class="product-colour-create__field">
				<span id="product-colour-create-code">Colour Code <strong>*</strong></span>
				<span class="product-colour-create__code">
					<ColorPicker :model-value="colourCode.replace('#', '')" :disabled="busy" @update:model-value="colourCode = `#${$event}`" />
					<InputText v-model="colourCode" fluid :disabled="busy" placeholder="#FF8800" aria-labelledby="product-colour-create-code" />
				</span>
			</div>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy" @click="setVisible(false)" />
			<Button type="submit" form="product-colour-create" label="Create" :loading="busy" />
		</template>
	</Dialog>
	<DocumentErrorDialog :message="actionError" title="Colour could not be created" @dismiss="actionError = ''" />
</template>

<script setup>
import Button from "primevue/button"
import ColorPicker from "primevue/colorpicker"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import { ref, watch } from "vue"

import { createColourCode } from "../../../api/pd.js"
import DocumentErrorDialog from "../../../components/documents/DocumentErrorDialog.vue"

const props = defineProps({
	visible: { type: Boolean, default: false },
	name: { type: String, default: "" },
})
const emit = defineEmits(["update:visible", "created"])
const colour = ref("")
const colourCode = ref("")
const busy = ref(false)
const actionError = ref("")

watch(() => props.visible, (visible) => {
	if (!visible) return
	colour.value = props.name
	colourCode.value = ""
	actionError.value = ""
})

function setVisible(visible) {
	if (!visible && busy.value) return
	emit("update:visible", visible)
}

async function save() {
	if (busy.value) return
	if (!colour.value.trim() || !colourCode.value.trim()) {
		actionError.value = "Colour and Colour Code are required."
		return
	}
	busy.value = true
	try {
		emit("created", await createColourCode(colour.value.trim(), colourCode.value.trim()))
		emit("update:visible", false)
	} catch (reason) {
		actionError.value = reason?.message || "Unable to create the colour."
	} finally {
		busy.value = false
	}
}
</script>

<style scoped>
.product-colour-create { display: grid; min-width: min(26rem, 75vw); gap: var(--erp-space-3); }
.product-colour-create__field { display: grid; gap: 7px; color: var(--erp-text); font-size: var(--erp-font-size-caption); font-weight: 680; }
.product-colour-create__field strong { color: var(--erp-danger); }
.product-colour-create__code { display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 8px; }
@media (max-width: 640px) { .product-colour-create { min-width: 0; } }
</style>
