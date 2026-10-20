export function productionOrderConfirmation(command, name = "this Production Order") {
	const messages = {
		delete: `Delete ${name}? This cannot be undone.`,
		cancel: `Cancel ${name}? Linked documents are checked before it is cancelled.`,
		amend: `Create an amended copy of ${name}?`,
		reopen: `Reopen ${name}?`,
		approve_ppo: `Approve and submit ${name}?`,
		request_ppo_approval: `Send ${name} for PPO approval?`,
		approve_status: `Approve the requested status change for ${name}?`,
		approve_quantity_ratio: `Approve the requested quantity and ratio changes for ${name}?`,
		approve_transfer: `Approve the incoming quantity transfer to ${name}?`,
	}
	return messages[command] || `Continue with this action for ${name}?`
}

const SUCCESS_MESSAGES = {
	delete: "Production Order deleted",
	cancel: "Production Order cancelled",
	amend: "Amended copy created",
	reopen: "Production Order reopened",
	request_ppo_approval: "PPO approval requested",
	approve_ppo: "PPO approved and submitted",
	request_changes: "PPO returned to Sales for changes",
	update_price: "Price update completed",
	change_dates: "Date change tracked",
	approve_status: "Status change approved",
	update_quantity_ratio: "Quantity & ratio update sent for approval",
	approve_quantity_ratio: "Quantity & ratio update approved",
	transfer_quantity: "Quantity transfer sent for approval",
	approve_transfer: "Transfer quantity approved",
	create_lot: "Lot created",
	link_lot: "Lot linked",
}

export function productionOrderSuccess(command, label, result = {}) {
	if (command === "change_status") return result.record?.status === "Pending Request" ? "Status change sent for approval" : "Status updated"
	return SUCCESS_MESSAGES[command] || `${label || "Production Order action"} done`
}
