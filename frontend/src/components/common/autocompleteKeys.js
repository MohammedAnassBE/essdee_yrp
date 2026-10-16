function isComposing(event) {
	return event.isComposing || event.keyCode === 229
}

export function withAutocompleteCompositionGuard(autocomplete) {
	return {
		...autocomplete,
		methods: {
			...autocomplete.methods,
			onKeyDown(event) {
				if (!isComposing(event)) autocomplete.methods.onKeyDown.call(this, event)
			},
		},
	}
}

export function handleAutocompleteKey(event, autocomplete, restore = () => {}, searching = false) {
	if (isComposing(event)) return
	if (!event.target || event.target !== autocomplete?.$el?.querySelector("input")) return
	if (event.key === "Enter") {
		event.preventDefault()
		event.stopPropagation()
		if (autocomplete?.overlayVisible && !searching) autocomplete.onEnterKey(event)
		return
	}
	if (event.key === "Escape") {
		restore()
		if (autocomplete?.overlayVisible) {
			autocomplete.hide()
			event.preventDefault()
			event.stopPropagation()
		}
	}
}
