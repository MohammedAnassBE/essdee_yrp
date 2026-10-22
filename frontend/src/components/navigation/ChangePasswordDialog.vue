<template>
	<Dialog
		:visible="visible"
		modal
		header="Change Password"
		class="erp-dialog--sm change-password-dialog"
		:closable="!busy"
		@update:visible="emit('update:visible', $event)"
		@show="reset"
	>
		<form id="change-password-form" class="change-password-dialog__form" novalidate @submit.prevent="submit">
			<label v-for="field in fields" :key="field.key" class="change-password-dialog__field">
				<span class="erp-field-label">{{ field.label }}</span>
				<InputText
					v-model="form[field.key]"
					:name="field.key"
					type="password"
					:autocomplete="field.autocomplete"
					:disabled="busy || done"
					fluid
					@input="field.key === 'newPassword' && scheduleStrengthCheck()"
				/>
			</label>
			<div v-if="strength" class="change-password-dialog__strength" :class="`is-${strength.tone}`" role="status">
				<strong>Password strength: {{ strength.label }}</strong>
				<span v-if="strength.warning">{{ strength.warning }}</span>
				<span v-for="suggestion in strength.suggestions" :key="suggestion">{{ suggestion }}</span>
			</div>
			<Message v-if="error" severity="error" :closable="false"><span class="change-password-dialog__message">{{ error }}</span></Message>
			<Message v-if="done" severity="success" :closable="false">Your new password has been set successfully.</Message>
		</form>
		<template #footer>
			<Button label="Cancel" severity="secondary" text :disabled="busy || done" @click="emit('update:visible', false)" />
			<Button type="submit" form="change-password-form" label="Change Password" icon="pi pi-key" :loading="busy" :disabled="done" />
		</template>
	</Dialog>
</template>

<script setup>
import Button from "primevue/button"
import Dialog from "primevue/dialog"
import InputText from "primevue/inputtext"
import Message from "primevue/message"
import { onBeforeUnmount, reactive, ref } from "vue"

import { changePassword, getPasswordStrength } from "../../api/account.js"

defineProps({ visible: { type: Boolean, default: false } })
const emit = defineEmits(["update:visible"])

const fields = [
	{ key: "oldPassword", label: "Current Password", autocomplete: "current-password" },
	{ key: "newPassword", label: "New Password", autocomplete: "new-password" },
	{ key: "confirmPassword", label: "Confirm New Password", autocomplete: "new-password" },
]
const form = reactive({ oldPassword: "", newPassword: "", confirmPassword: "" })
const strength = ref(null)
const error = ref("")
const busy = ref(false)
const done = ref(false)
let strengthTimer = null

function reset() {
	Object.assign(form, { oldPassword: "", newPassword: "", confirmPassword: "" })
	strength.value = null
	error.value = ""
	done.value = false
}

function scheduleStrengthCheck() {
	clearTimeout(strengthTimer)
	strengthTimer = setTimeout(async () => {
		const password = form.newPassword
		const result = await getPasswordStrength(password).catch(() => null)
		if (password === form.newPassword) strength.value = result
	}, 300)
}

async function submit() {
	busy.value = true
	error.value = ""
	try {
		await changePassword(form)
		done.value = true
		// Frappe signs the user in again with a new session; reload so /web uses its CSRF token.
		setTimeout(() => window.location.reload(), 2000)
	} catch (failure) {
		error.value = failure.message
	} finally {
		busy.value = false
	}
}

onBeforeUnmount(() => clearTimeout(strengthTimer))
</script>

<style scoped>
.change-password-dialog__form { display: grid; gap: var(--erp-space-3, 12px); }
.change-password-dialog__field { display: grid; gap: var(--erp-space-1, 4px); }
.change-password-dialog__strength { display: grid; gap: 2px; font-size: var(--erp-font-size-caption); color: var(--erp-text-secondary); }
.change-password-dialog__strength.is-danger strong { color: var(--erp-danger, var(--p-red-600)); }
.change-password-dialog__strength.is-warn strong { color: var(--p-orange-600); }
.change-password-dialog__strength.is-info strong { color: var(--erp-accent); }
.change-password-dialog__strength.is-success strong { color: var(--p-green-600); }
.change-password-dialog__message { white-space: pre-line; overflow-wrap: anywhere; }
</style>
