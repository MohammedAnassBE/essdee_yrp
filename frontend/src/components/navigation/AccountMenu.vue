<template>
	<button type="button" class="app-theme-toggle app-logout" aria-label="Log out" title="Log out" @click="confirmation.open('logout')">
		<i class="pi pi-sign-out" aria-hidden="true" />
		<span>Log out</span>
	</button>
	<button
		type="button"
		class="app-theme-toggle app-account-menu-button"
		aria-label="Account options"
		title="Account options"
		aria-haspopup="menu"
		:aria-expanded="menuOpen"
		@click="menu.toggle($event)"
	>
		<i class="pi pi-ellipsis-v" aria-hidden="true" />
	</button>
	<Menu ref="menu" :model="menuItems" popup class="app-account-menu" @show="menuOpen = true" @hide="menuOpen = false" />

	<DocumentConfirmationDialog
		:visible="Boolean(confirmation.current.value)"
		:title="confirmation.current.value?.title"
		:message="confirmation.current.value?.message"
		:confirm-label="confirmation.current.value?.confirmLabel"
		:confirm-icon="confirmation.current.value?.confirmIcon"
		:severity="confirmation.current.value?.severity"
		cancel-label="Cancel"
		icon="pi pi-sign-out"
		:busy="confirmation.busy.value"
		@update:visible="(open) => { if (!open) confirmation.cancel() }"
		@confirm="confirmation.confirm"
	>
		<Message v-if="confirmation.error.value" severity="error" :closable="false">{{ confirmation.error.value }}</Message>
	</DocumentConfirmationDialog>
	<ChangePasswordDialog v-model:visible="changingPassword" />
</template>

<script setup>
import Menu from "primevue/menu"
import Message from "primevue/message"
import { ref } from "vue"

import DocumentConfirmationDialog from "../documents/DocumentConfirmationDialog.vue"
import ChangePasswordDialog from "./ChangePasswordDialog.vue"
import { createAccountConfirmation } from "./accountMenu.js"

const menu = ref(null)
const menuOpen = ref(false)
const changingPassword = ref(false)
const confirmation = createAccountConfirmation()
const menuItems = [
	{ label: "Change Password", icon: "pi pi-key", command: () => { changingPassword.value = true } },
	{ label: "Log out from all devices", icon: "pi pi-sign-out", class: "app-account-menu__item--danger", command: () => confirmation.open("logout-all") },
]
</script>
