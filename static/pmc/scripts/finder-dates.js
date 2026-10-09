(function () {
	var MILLISECONDS_PER_DAY = 86400000
	var MAX_DAYS_SHOWN_AS_COUNT = 6

	function parseLocalDate(isoDate) {
		var parts = isoDate.split('-').map(Number)
		return new Date(parts[0], parts[1] - 1, parts[2])
	}

	function daysUntil(isoDate) {
		var today = new Date()
		today.setHours(0, 0, 0, 0)
		return Math.round((parseLocalDate(isoDate) - today) / MILLISECONDS_PER_DAY)
	}

	function relativeEventDayLabel(isoDate) {
		var days = daysUntil(isoDate)
		if (days === 0) return 'today'
		if (days === 1) return 'tomorrow'
		if (days > 1 && days <= MAX_DAYS_SHOWN_AS_COUNT) return 'in ' + days + ' days'
		return parseLocalDate(isoDate).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
	}

	function relabelRelativeEventDays(root) {
		root.querySelectorAll('time[data-relative-event-day]').forEach(function (element) {
			element.textContent = relativeEventDayLabel(element.getAttribute('datetime'))
		})
	}

	window.FinderDates = {
		parseLocalDate: parseLocalDate,
		daysUntil: daysUntil,
		relabelRelativeEventDays: relabelRelativeEventDays,
	}

	relabelRelativeEventDays(document)
	document.addEventListener('htmx:afterSwap', function (event) {
		relabelRelativeEventDays(event.detail.target)
	})
}())
