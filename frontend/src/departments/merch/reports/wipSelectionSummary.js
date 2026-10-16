export function selectionSummary(values, chipWidths, availableWidth) {
	let visibleCount = 0
	let row = 1
	let usedWidth = 0
	for (const width of chipWidths.slice(0, 6)) {
		const chipWidth = Math.min(width, availableWidth)
		const gap = usedWidth ? 5 : 0
		if (usedWidth + gap + chipWidth > availableWidth) {
			row += 1
			usedWidth = 0
		}
		if (row > 2 || visibleCount >= values.length) break
		usedWidth += (usedWidth ? 5 : 0) + chipWidth
		visibleCount += 1
	}
	return { visible: values.slice(0, visibleCount), hiddenCount: values.length - visibleCount }
}
