<template>
	<SplitButton
		v-if="showSave && showSubmit"
		class="document-save-button"
		:label="saveLabel"
		:icon="loading ? 'pi pi-spinner pi-spin' : 'pi pi-save'"
		:model="submitItems"
		:aria-busy="loading"
		:disabled="loading || disabled || (saveDisabled && submitDisabled)"
		:button-props="{ disabled: loading || disabled || saveDisabled }"
		:menu-button-props="{ 'aria-label': `${saveLabel} options`, disabled: loading || disabled || submitDisabled }"
		@click="emit('save')"
	/>
	<Button
		v-else-if="showSubmit"
		class="document-save-button"
		:label="submitLabel"
		icon="pi pi-check"
		:loading="loading"
		:disabled="loading || disabled || submitDisabled"
		@click="emit('submit')"
	/>
	<Button
		v-else-if="showSave"
		class="document-save-button"
		:label="saveLabel"
		icon="pi pi-save"
		:loading="loading"
		:disabled="loading || disabled || saveDisabled"
		@click="emit('save')"
	/>
</template>

<script setup>
import Button from "primevue/button"
import SplitButton from "primevue/splitbutton"
import { computed } from "vue"

const props = defineProps({
	showSave: { type: Boolean, default: true },
	showSubmit: { type: Boolean, default: false },
	saveLabel: { type: String, default: "Save" },
	submitLabel: { type: String, default: "Save & Submit" },
	loading: { type: Boolean, default: false },
	disabled: { type: Boolean, default: false },
	saveDisabled: { type: Boolean, default: false },
	submitDisabled: { type: Boolean, default: false },
})
const emit = defineEmits(["save", "submit"])
const submitItems = computed(() => [{ label: props.submitLabel, icon: "pi pi-check", disabled: props.loading || props.disabled || props.submitDisabled, command: () => emit("submit") }])
</script>

<style scoped>
.document-save-button { white-space: nowrap; }
</style>
