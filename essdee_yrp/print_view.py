def set_print_view_title(context):
	"""Title /printview after the document so the browser's Save as PDF names the file after it.

	Frappe swaps the title only on `beforeprint`, which registers after the
	`trigger_print=1` script has already called `window.print()`.
	"""
	if context.get("template") == "www/printview.html" and context.get("print_filename"):
		return {"title": context["print_filename"]}
