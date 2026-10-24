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
		v-if="confirmationLoaded"
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
	<ChangePasswordDialog v-if="passwordDialogLoaded" v-model:visible="changingPassword" />
</template>

<script setup>
import Menu from "primevue/menu"
import { defineAsyncComponent, ref, watch } from "vue"

import { createAccountConfirmation } from "./accountMenu.js"

// Lazy: the dialogs are loaded on first use, so they stay out of the entry chunk.
const DocumentConfirmationDialog = defineAsyncComponent(() => import("../documents/DocumentConfirmationDialog.vue"))
const ChangePasswordDialog = defineAsyncComponent(() => import("./ChangePasswordDialog.vue"))
const Message = defineAsyncComponent(() => import("primevue/message"))

const menu = ref(null)
const menuOpen = ref(false)
const changingPassword = ref(false)
const confirmation = createAccountConfirmation()
const confirmationLoaded = ref(false)
const passwordDialogLoaded = ref(false)
watch(() => confirmation.current.value, (current) => { if (current) confirmationLoaded.value = true })
watch(changingPassword, (open) => { if (open) passwordDialogLoaded.value = true })
const menuItems = [
	{ label: "Change Password", icon: "pi pi-key", command: () => { changingPassword.value = true } },
	{ label: "Log out from all devices", icon: "pi pi-sign-out", class: "app-account-menu__item--danger", command: () => confirmation.open("logout-all") },
]
</script>
