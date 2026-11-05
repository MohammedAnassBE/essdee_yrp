frappe.listview_settings["YRP Work Order"] = frappe.listview_settings["YRP Work Order"] || {};

(() => {
	const settings = frappe.listview_settings["YRP Work Order"];
	const base_onload = settings.onload;
	const APPROVE_METHOD =
		"essdee_yrp.essdee_yrp.page.work_order_bulk_close.work_order_bulk_close.approve_close_requests";

	const plural = (count, one, many) => (count === 1 ? __(one) : __(many, [count]));

	function show_approve_result({ approved = [], failed = [] }) {
		const closed = plural(approved.length, "1 Work Order closed.", "{0} Work Orders closed.");
		if (!failed.length) {
			frappe.show_alert({ message: closed, indicator: "green" });
			return;
		}
		const failures = failed
			.map(
				(failure) =>
					`<li><strong>${frappe.utils.escape_html(failure.work_order)}</strong> — ${frappe.utils.escape_html(failure.error)}</li>`
			)
			.join("");
		frappe.msgprint({
			title: __("Bulk Approve Close Result"),
			indicator: approved.length ? "orange" : "red",
			message: `<p>${closed}</p><p>${plural(failed.length, "1 Work Order failed:", "{0} Work Orders failed:")}</p><ul>${failures}</ul>`,
			wide: true,
		});
	}

	function approve_close(listview) {
		const names = listview.get_checked_items(true);
		if (!names.length) {
			frappe.msgprint(__("Select at least one Work Order to approve."));
			return;
		}
		frappe.confirm(__("Approve close for {0} selected Work Orders?", [names.length]), () =>
			frappe
				.call({
					method: APPROVE_METHOD,
					args: { work_orders: names },
					freeze: true,
					freeze_message: __("Approving selected Work Orders..."),
				})
				.then((response) => {
					show_approve_result(response.message || {});
					listview.refresh();
				})
		);
	}

	settings.onload = function (listview) {
		base_onload?.call(this, listview);
		frappe
			.xcall("yrp.yrp.doctype.yrp_work_order.yrp_work_order.get_close_permission")
			.then((permission) => {
				if (permission?.is_close_manager) {
					listview.page.add_actions_menu_item(__("Approve Close"), () => approve_close(listview));
				}
			});
	};
})();
