export function createDebouncedSearch(search, handlers, timers = {}) {
	const schedule = timers.schedule || setTimeout
	const cancelSchedule = timers.cancel || clearTimeout
	const delay = timers.delay ?? 250
	let sequence = 0
	let timer = null

	function invalidate() {
		sequence += 1
		if (timer !== null) cancelSchedule(timer)
		timer = null
		return sequence
	}

	async function run(query, requestSequence) {
		try {
			const result = await search(query)
			if (requestSequence === sequence) handlers.onResult(result)
		} catch (reason) {
			if (requestSequence === sequence) handlers.onError(reason)
		} finally {
			if (requestSequence === sequence) handlers.onSettled()
		}
	}

	function queue(query) {
		const requestSequence = invalidate()
		timer = schedule(() => {
			timer = null
			void run(query, requestSequence)
		}, delay)
	}

	function load(query) {
		return run(query, invalidate())
	}

	return { invalidate, load, queue }
}
