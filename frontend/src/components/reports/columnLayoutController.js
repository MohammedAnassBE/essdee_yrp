import { clampColumnWidth, headerGrid, moveColumnLabel, uniqueColumnLabels } from "./columnLayout.js"

const HANDLE_CLASS = "report-col-resize"
const SIZED_CLASS = "is-column-sized"
const MOVABLE_CLASS = "is-column-movable"
const DRAG_THRESHOLD = 6
const INTERACTIVE = "input, textarea, select, button, a, [contenteditable]"

/** Layout key of a table: an explicit data-column-layout, else its caption or region label. */
export function tableLayoutKey(table, index) {
	return table.dataset.columnLayout
		|| table.caption?.textContent?.trim()
		|| table.closest("[aria-label]")?.getAttribute("aria-label")
		|| `table-${index + 1}`
}

function isPinnedCell(cell) {
	const style = cell.ownerDocument.defaultView.getComputedStyle(cell)
	return style.position === "sticky" && style.left !== "auto"
}

/** Header model of a table: one entry per column with its leaf header cell and label. */
export function tableColumns(table) {
	const { cells, columnCount } = headerGrid([...(table.tHead?.rows || [])])
	const leaves = Array.from({ length: columnCount }, () => null)
	for (const entry of cells) if (entry.span === 1) leaves[entry.column] = entry.cell
	const labels = uniqueColumnLabels(leaves.map((cell, index) => cell ? cell.textContent.trim() || `#${index + 1}` : `#${index + 1}`))
	return leaves.map((cell, index) => ({ cell, index, label: labels[index] }))
}

function widthSignature(columns, saved) {
	return JSON.stringify(columns.map(column => [column.label, saved[column.label] ?? null]))
}

function ownColgroup(table) {
	return [...table.children].find(child => child.dataset?.columnLayout === "widths") || null
}

function unsizeTable(table) {
	ownColgroup(table)?.remove()
	for (const group of table.querySelectorAll(":scope > colgroup")) group.style.removeProperty("display")
	for (const property of ["table-layout", "width", "min-width", "max-width"]) table.style.removeProperty(property)
	table.classList.remove(SIZED_CLASS)
	delete table.dataset.columnWidths
}

/** Fixed table layout with one `<col>` per column, so each width holds regardless of cell content. */
export function sizeTable(table, columns, saved) {
	const signature = widthSignature(columns, saved)
	if (table.dataset.columnWidths === signature && ownColgroup(table)) return
	unsizeTable(table)
	const widths = columns.map(column => saved[column.label] ? clampColumnWidth(saved[column.label]) : Math.ceil(column.cell?.getBoundingClientRect().width || 0))
	for (const group of table.querySelectorAll(":scope > colgroup")) group.style.display = "none"
	const colgroup = table.ownerDocument.createElement("colgroup")
	colgroup.dataset.columnLayout = "widths"
	for (const width of widths) {
		const col = table.ownerDocument.createElement("col")
		col.style.width = `${width}px`
		colgroup.append(col)
	}
	table.insertBefore(colgroup, table.caption ? table.caption.nextSibling : table.firstChild)
	setTableWidth(table, widths.reduce((total, width) => total + width, 0))
	table.classList.add(SIZED_CLASS)
	table.dataset.columnWidths = signature
}

function setTableWidth(table, width) {
	for (const property of ["width", "min-width", "max-width"]) table.style.setProperty(property, `${width}px`)
	table.style.tableLayout = "fixed"
}

function ensureHandle(cell) {
	if (cell.querySelector(`:scope > .${HANDLE_CLASS}`)) return
	if (cell.ownerDocument.defaultView.getComputedStyle(cell).position === "static") cell.style.position = "relative"
	const handle = cell.ownerDocument.createElement("span")
	handle.className = HANDLE_CLASS
	handle.dataset.captureHide = ""
	handle.setAttribute("aria-hidden", "true")
	handle.title = "Drag to resize. Double-click to reset."
	cell.append(handle)
}

/**
 * Adds drag-to-resize handles to every report table under `root` and, on tables marked data-column-order,
 * drag-to-move headers. Widths and order live in `layout` ({ widths, order } keyed by table layout key).
 */
export function attachColumnLayout(root, layout) {
	const view = root.ownerDocument.defaultView
	let frame = 0

	function syncTable(table, index) {
		const key = tableLayoutKey(table, index)
		const columns = tableColumns(table)
		const isMovable = table.hasAttribute("data-column-order")
		for (const column of columns) {
			if (!column.cell || isPinnedCell(column.cell)) continue
			ensureHandle(column.cell)
			column.cell.classList.toggle(MOVABLE_CLASS, isMovable)
		}
		const saved = layout.widths[key] || {}
		if (columns.some(column => saved[column.label])) sizeTable(table, columns, saved)
		else if (table.classList.contains(SIZED_CLASS)) unsizeTable(table)
	}

	function sync() {
		frame = 0
		root.querySelectorAll("table").forEach((table, index) => { if (table.tHead) syncTable(table, index) })
	}

	function scheduleSync() {
		if (!frame) frame = view.requestAnimationFrame(sync)
	}

	function locate(cell) {
		const table = cell.closest("table")
		const index = [...root.querySelectorAll("table")].indexOf(table)
		return { table, key: tableLayoutKey(table, index), columns: tableColumns(table) }
	}

	/** The column a handle sits in now; headers move with their handles when the column order changes. */
	function locateHandle(handle) {
		const located = locate(handle)
		return { ...located, column: located.columns.find(column => column.cell === handle.parentElement) }
	}

	function beginResize(event, handle) {
		const { table, key, columns, column } = locateHandle(handle)
		if (!column) return
		const saved = { ...(layout.widths[key] || {}), [column.label]: clampColumnWidth(column.cell.getBoundingClientRect().width) }
		// Saved before the drag so a sync mid-drag finds the table already sized and leaves it alone.
		layout.widths = { ...layout.widths, [key]: saved }
		sizeTable(table, columns, saved)
		const startX = event.clientX, startWidth = saved[column.label]
		let width = startWidth
		const onMove = moveEvent => {
			width = clampColumnWidth(startWidth + moveEvent.clientX - startX)
			const cols = [...ownColgroup(table).children]
			cols[column.index].style.width = `${width}px`
			setTableWidth(table, cols.reduce((total, col) => total + parseFloat(col.style.width), 0))
		}
		trackPointer(event, handle, "is-column-resizing", onMove, () => {
			const widths = { ...saved, [column.label]: width }
			table.dataset.columnWidths = widthSignature(columns, widths)
			layout.widths = { ...layout.widths, [key]: widths }
		})
	}

	function resetWidth(handle) {
		const { key, column } = locateHandle(handle)
		const label = column?.label
		const { [label]: _removed, ...rest } = layout.widths[key] || {}
		const { [key]: _table, ...others } = layout.widths
		layout.widths = Object.keys(rest).length ? { ...others, [key]: rest } : others
		sync()
	}

	function beginMove(event, cell) {
		const { table, key, columns } = locate(cell)
		const movable = columns.filter(column => column.cell && !isPinnedCell(column.cell))
		const from = movable.find(column => column.cell === cell)
		if (!from) return
		const startX = event.clientX
		let target = null, indicator = null
		const scroller = scrollParent(table)
		const onMove = moveEvent => {
			if (!indicator && Math.abs(moveEvent.clientX - startX) < DRAG_THRESHOLD) return
			indicator ||= createIndicator(table)
			scrollNearEdge(scroller, moveEvent.clientX)
			target = dropTarget(movable, moveEvent.clientX)
			placeIndicator(indicator, table, target.x)
		}
		trackPointer(event, cell, "is-column-moving", onMove, () => {
			indicator?.remove()
			if (!indicator || !target) return
			suppressNextClick(cell)
			const labels = movable.map(column => column.label)
			const next = moveColumnLabel(labels, from.label, target.index)
			if (next.join("\n") !== labels.join("\n")) layout.order = { ...layout.order, [key]: next }
		})
	}

	function onPointerDown(event) {
		if (event.button !== 0) return
		const handle = event.target.closest?.(`.${HANDLE_CLASS}`)
		if (handle && root.contains(handle)) { event.preventDefault(); event.stopPropagation(); beginResize(event, handle); return }
		const cell = event.target.closest?.(`th.${MOVABLE_CLASS}`)
		if (!cell || !root.contains(cell) || event.target.closest(INTERACTIVE)) return
		beginMove(event, cell)
	}

	function onDoubleClick(event) {
		const handle = event.target.closest?.(`.${HANDLE_CLASS}`)
		if (handle && root.contains(handle)) { event.preventDefault(); resetWidth(handle) }
	}

	const observer = new view.MutationObserver(scheduleSync)
	observer.observe(root, { childList: true, subtree: true, characterData: true })
	root.addEventListener("pointerdown", onPointerDown)
	root.addEventListener("dblclick", onDoubleClick)
	sync()
	return {
		sync,
		detach() {
			observer.disconnect()
			if (frame) view.cancelAnimationFrame(frame)
			root.removeEventListener("pointerdown", onPointerDown)
			root.removeEventListener("dblclick", onDoubleClick)
		},
	}
}

/** Nearest column boundary to `x` among the movable header cells: index 0 is before the first, length is after the last. */
export function dropTarget(columns, x) {
	const edges = columns.map(column => column.cell.getBoundingClientRect())
	const boundaries = [{ index: 0, x: edges[0].left }, ...edges.map((rect, index) => ({ index: index + 1, x: rect.right }))]
	return boundaries.reduce((best, boundary) => Math.abs(boundary.x - x) < Math.abs(best.x - x) ? boundary : best)
}

const EDGE_SCROLL_ZONE = 40
const EDGE_SCROLL_STEP = 24

function scrollParent(table) {
	const view = table.ownerDocument.defaultView
	for (let node = table.parentElement; node; node = node.parentElement) {
		if (/auto|scroll/.test(view.getComputedStyle(node).overflowX)) return node
	}
	return null
}

/** Scrolls a wide table sideways while a dragged header is held near the edge of its scroll box. */
function scrollNearEdge(scroller, x) {
	if (!scroller) return
	const rect = scroller.getBoundingClientRect()
	if (x < rect.left + EDGE_SCROLL_ZONE) scroller.scrollLeft -= EDGE_SCROLL_STEP
	else if (x > rect.right - EDGE_SCROLL_ZONE) scroller.scrollLeft += EDGE_SCROLL_STEP
}

function trackPointer(event, element, bodyClass, onMove, onEnd) {
	const doc = element.ownerDocument
	element.setPointerCapture?.(event.pointerId)
	doc.body.classList.add(bodyClass)
	const end = () => {
		element.removeEventListener("pointermove", onMove)
		element.removeEventListener("pointerup", end)
		element.removeEventListener("pointercancel", end)
		doc.body.classList.remove(bodyClass)
		onEnd()
	}
	element.addEventListener("pointermove", onMove)
	element.addEventListener("pointerup", end)
	element.addEventListener("pointercancel", end)
}

function suppressNextClick(element) {
	const view = element.ownerDocument.defaultView
	const stop = event => { event.stopPropagation(); event.preventDefault() }
	view.addEventListener("click", stop, { capture: true, once: true })
	view.setTimeout(() => view.removeEventListener("click", stop, { capture: true }), 0)
}

function createIndicator(table) {
	const indicator = table.ownerDocument.createElement("div")
	indicator.className = "report-col-drop-indicator"
	indicator.setAttribute("aria-hidden", "true")
	table.ownerDocument.body.append(indicator)
	return indicator
}

function placeIndicator(indicator, table, x) {
	const rect = table.getBoundingClientRect()
	const view = table.ownerDocument.defaultView
	const top = Math.max(rect.top, 0)
	indicator.style.left = `${x - 1}px`
	indicator.style.top = `${top}px`
	indicator.style.height = `${Math.max(0, Math.min(rect.bottom, view.innerHeight) - top)}px`
}
