import frappe
from frappe.realtime import get_user_room
from frappe.utils.background_jobs import get_queue_args, truncate_failed_registry

DONE_EVENT = "yrp_laysheet_job_done"
STATUS_TTL_SECONDS = 6 * 60 * 60


def enqueue_tracked_job(target: str, doctype: str, docname: str, **target_kwargs) -> dict:
	"""Enqueue `target(**target_kwargs)` after commit; the returned token reports when that job ends."""
	token = frappe.generate_hash(length=20)
	_store_status(token, doctype, docname, "queued")
	frappe.enqueue(
		run_tracked_job,
		"short",
		enqueue_after_commit=True,
		on_failure=on_tracked_job_failure,
		target=target,
		token=token,
		doctype=doctype,
		docname=docname,
		user=frappe.session.user,
		target_kwargs=target_kwargs,
	)
	return {"job_token": token}


def run_tracked_job(target: str, token: str, doctype: str, docname: str, user: str, target_kwargs: dict):
	"""Worker entry: runs the job and reports success to the user who queued it once the job commits.

	Failures are left to `on_tracked_job_failure`: Frappe's `execute_job` retries deadlocks, lock
	timeouts and `RetryBackgroundJobError` in place, so an exception here may not be the job's end.
	"""
	_store_status(token, doctype, docname, "running")
	frappe.get_attr(target)(**target_kwargs)
	frappe.db.after_commit.add(lambda: _finish(token, doctype, docname, user, "finished"))


def on_tracked_job_failure(job, connection, *exc_info):
	"""RQ failure callback: runs only once the job has failed for good (retries exhausted, error or timeout)."""
	truncate_failed_registry(job, connection, *exc_info)
	queue_args = get_queue_args(job)
	kwargs = queue_args.get("kwargs") or {}
	if not kwargs.get("token"):
		return
	owns_site = not getattr(frappe.local, "site", None)
	if owns_site:
		frappe.init(queue_args["site"], force=True)
	try:
		_finish(kwargs["token"], kwargs["doctype"], kwargs["docname"], kwargs["user"], "failed")
	finally:
		if owns_site:
			frappe.destroy()


@frappe.whitelist()
def get_tracked_job_status(job_token: str) -> dict:
	"""Fallback for clients that missed the realtime event."""
	state = frappe.cache.get_value(_cache_key(job_token))
	if not state:
		return {"status": "unknown"}
	frappe.has_permission(state["doctype"], "read", state["docname"], throw=True)
	return {"status": state["status"]}


def _finish(token: str, doctype: str, docname: str, user: str, status: str):
	_store_status(token, doctype, docname, status)
	frappe.publish_realtime(
		DONE_EVENT,
		{"job_token": token, "doctype": doctype, "name": docname, "status": status},
		room=get_user_room(user),
	)


def _store_status(token: str, doctype: str, docname: str, status: str):
	value = {"doctype": doctype, "docname": docname, "status": status}
	frappe.cache.set_value(_cache_key(token), value, expires_in_sec=STATUS_TTL_SECONDS)


def _cache_key(token: str) -> str:
	return f"yrp_laysheet_job:{token}"
