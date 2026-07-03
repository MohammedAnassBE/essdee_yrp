import { ref } from "vue"

// Shared open-state for the ⌘K command palette so the topbar search trigger and
// the global keyboard shortcut both drive the single <CommandPalette/> instance
// mounted in AppLayout.
const open = ref(false)

export function useCommandPalette() {
	return {
		open,
		openPalette: () => { open.value = true },
		closePalette: () => { open.value = false },
		togglePalette: () => { open.value = !open.value },
	}
}
