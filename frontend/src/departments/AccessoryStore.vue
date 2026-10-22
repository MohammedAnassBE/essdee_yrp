<template>
	<FabricStore store-name="Accessory Store" base-path="/accessory-store" :workspace-keys="ACCESSORY_STORE_WORKSPACE_KEYS" />
</template>

<script setup>
import FabricStore from "./FabricStore.vue"
import { ACCESSORY_STORE_WORKSPACE_KEYS } from "./fabric-store/storeWorkspaces.js"
</script>
