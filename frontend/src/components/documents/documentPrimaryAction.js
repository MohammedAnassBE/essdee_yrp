export function getDocumentPrimaryAction({ saved, dirty, docstatus = 0, showSave = true, showSubmit = false, allowUpdateAfterSubmit = false }) {
	if (docstatus === 1 && allowUpdateAfterSubmit) return dirty ? "save" : "save-disabled"
	if (docstatus >= 1 || (!showSave && !showSubmit)) return "none"
	if (!showSave && showSubmit) return "submit"
	if (!saved || dirty) return "save"
	return showSubmit ? "submit" : "save-disabled"
}
