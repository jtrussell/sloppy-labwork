(function () {
	var RESULTS_PAGE_SIZE = 20
	var SHEET_STATES = ['peek', 'half', 'full']
	var MOBILE_MEDIA_QUERY = window.matchMedia('(max-width: 680px)')

	var map = L.map('finder-map', { zoomControl: false }).setView([30, 0], 2)
	L.control.zoom({ position: 'bottomright' }).addTo(map)

	L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
		attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
		maxZoom: 19,
	}).addTo(map)

	var primaryIcon = L.divIcon({
		className: 'finder-marker finder-marker-primary',
		html: '<svg viewBox="0 0 24 36" width="28" height="40"><path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z" fill="#FFB400" stroke="#131313" stroke-width="1.5"/><circle cx="12" cy="11" r="5" fill="#131313"/></svg>',
		iconSize: [28, 40],
		iconAnchor: [14, 40],
		popupAnchor: [0, -36],
	})

	var secondaryIcon = L.divIcon({
		className: 'finder-marker finder-marker-secondary',
		html: '<svg viewBox="0 0 24 36" width="22" height="32"><path d="M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z" fill="#888" stroke="#131313" stroke-width="1.5"/><circle cx="12" cy="11" r="4" fill="#131313"/></svg>',
		iconSize: [22, 32],
		iconAnchor: [11, 32],
		popupAnchor: [0, -28],
	})

	var markers = L.markerClusterGroup({
		showCoverageOnHover: false,
		maxClusterRadius: 50,
	}).addTo(map)

	var allPlaygroups = []
	var markersByPlaygroupVenue = {}
	var visiblePlaygroups = []
	var currentPage = 1
	var activePlaygroupId = null
	var debounceTimer = null
	var inFlightRequest = null

	var panel = document.getElementById('finder-panel')
	var sheetHandle = document.getElementById('finder-sheet-handle')
	var menuToggle = document.getElementById('finder-menu-toggle')
	var chrome = document.getElementById('finder-chrome')
	var searchInput = document.getElementById('finder-search-input')
	var upcomingEventsInput = document.getElementById('finder-upcoming-events')
	var eventFormatInput = document.getElementById('finder-event-format')
	var resultsSummary = document.getElementById('finder-results-summary')
	var resultsList = document.getElementById('finder-results')
	var pagination = document.getElementById('finder-pagination')
	var previousPageButton = document.getElementById('finder-page-previous')
	var nextPageButton = document.getElementById('finder-page-next')
	var pageLabel = document.getElementById('finder-page-label')

	function escapeHtml(str) {
		var div = document.createElement('div')
		div.textContent = str
		return div.innerHTML
	}

	function pluralize(count, singular, plural) {
		return count + ' ' + (count === 1 ? singular : plural)
	}

	function markerKey(playgroupId, venueId) {
		return playgroupId + ':' + venueId
	}

	function buildPopupHtml(playgroup, venue) {
		var primaryLabel = venue.is_primary ? ' (Primary)' : ''
		var locationParts = []
		if (venue.city) locationParts.push(escapeHtml(venue.city))
		if (venue.state_province) locationParts.push(escapeHtml(venue.state_province))
		return '<div class="finder-popup">' +
			'<div class="finder-popup-header">' +
				'<img class="finder-popup-logo" src="' + escapeHtml(playgroup.logo_src) + '" alt="" />' +
				'<div class="finder-popup-name"><a href="' + escapeHtml(playgroup.url) + '">' + escapeHtml(playgroup.name) + '</a></div>' +
			'</div>' +
			'<div class="finder-popup-venue">' + escapeHtml(venue.name) + primaryLabel + '</div>' +
			(locationParts.length ? '<div class="finder-popup-meta">' + locationParts.join(', ') + '</div>' : '') +
			'<div class="finder-popup-meta">' + pluralize(playgroup.member_count, 'member', 'members') + '</div>' +
		'</div>'
	}

	function renderMarkers() {
		markers.clearLayers()
		markersByPlaygroupVenue = {}
		var newMarkers = []
		allPlaygroups.forEach(function (playgroup) {
			playgroup.venues.forEach(function (venue) {
				var icon = venue.is_primary ? primaryIcon : secondaryIcon
				var marker = L.marker([venue.latitude, venue.longitude], { icon: icon })
				marker.bindPopup(buildPopupHtml(playgroup, venue))
				markersByPlaygroupVenue[markerKey(playgroup.id, venue.id)] = marker
				newMarkers.push(marker)
			})
		})
		markers.addLayers(newMarkers)
	}

	function fitMapToAllPlaygroups() {
		var bounds = []
		allPlaygroups.forEach(function (playgroup) {
			playgroup.venues.forEach(function (venue) {
				bounds.push([venue.latitude, venue.longitude])
			})
		})
		if (bounds.length > 0) {
			map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 })
		}
	}

	function findVenuesInView(playgroup) {
		var mapBounds = map.getBounds()
		return playgroup.venues.filter(function (venue) {
			return mapBounds.contains([venue.latitude, venue.longitude])
		})
	}

	function findPreferredVenue(playgroup) {
		var venuesInView = findVenuesInView(playgroup)
		var candidates = venuesInView.length ? venuesInView : playgroup.venues
		return candidates.find(function (venue) { return venue.is_primary }) || candidates[0]
	}

	function pageCount() {
		return Math.max(1, Math.ceil(visiblePlaygroups.length / RESULTS_PAGE_SIZE))
	}

	function pageContainingActivePlaygroup() {
		var activeIndex = visiblePlaygroups.findIndex(function (playgroup) {
			return playgroup.id === activePlaygroupId
		})
		return activeIndex === -1 ? 1 : Math.floor(activeIndex / RESULTS_PAGE_SIZE) + 1
	}

	function refreshVisiblePlaygroups() {
		visiblePlaygroups = allPlaygroups.filter(function (playgroup) {
			return findVenuesInView(playgroup).length > 0
		})
		currentPage = pageContainingActivePlaygroup()
		renderResults()
	}

	function renderSummary() {
		resultsSummary.innerHTML = ''

		if (allPlaygroups.length === 0) {
			resultsSummary.textContent = 'No groups match your search.'
			return
		}

		if (visiblePlaygroups.length === 0) {
			resultsSummary.appendChild(document.createTextNode('No groups in this area. '))
			resultsSummary.appendChild(buildShowAllButton())
			return
		}

		var firstShown = (currentPage - 1) * RESULTS_PAGE_SIZE + 1
		var lastShown = Math.min(currentPage * RESULTS_PAGE_SIZE, visiblePlaygroups.length)
		var summaryText = visiblePlaygroups.length > RESULTS_PAGE_SIZE
			? firstShown + '–' + lastShown + ' of ' + pluralize(visiblePlaygroups.length, 'group', 'groups') + ' in this area'
			: pluralize(visiblePlaygroups.length, 'group', 'groups') + ' in this area'
		resultsSummary.appendChild(document.createTextNode(summaryText))

		var hiddenCount = allPlaygroups.length - visiblePlaygroups.length
		if (hiddenCount > 0) {
			resultsSummary.appendChild(document.createTextNode(' • '))
			resultsSummary.appendChild(buildShowAllButton(hiddenCount + ' more outside view'))
		}
	}

	function buildShowAllButton(label) {
		var button = document.createElement('button')
		button.type = 'button'
		button.className = 'finder-link-button'
		button.textContent = label || 'Show all'
		button.addEventListener('click', fitMapToAllPlaygroups)
		return button
	}

	function renderPagination() {
		var totalPages = pageCount()
		pagination.hidden = totalPages <= 1
		previousPageButton.disabled = currentPage <= 1
		nextPageButton.disabled = currentPage >= totalPages
		pageLabel.textContent = 'Page ' + currentPage + ' of ' + totalPages
	}

	function buildResultItem(playgroup) {
		var li = document.createElement('li')
		li.setAttribute('data-pg-id', playgroup.id)
		li.tabIndex = 0
		li.setAttribute('role', 'button')
		if (playgroup.id === activePlaygroupId) {
			li.classList.add('active')
		}

		var img = document.createElement('img')
		img.src = playgroup.logo_src
		img.alt = ''
		img.className = 'finder-result-logo'

		var info = document.createElement('div')
		info.className = 'finder-result-info'

		var nameSpan = document.createElement('span')
		nameSpan.className = 'finder-result-name'
		nameSpan.textContent = playgroup.name

		var metaSpan = document.createElement('span')
		metaSpan.className = 'finder-result-meta'
		var metaParts = [pluralize(playgroup.member_count, 'member', 'members')]
		if (playgroup.type) {
			metaParts.push(playgroup.type)
		}
		metaSpan.textContent = metaParts.join(' • ')

		info.appendChild(nameSpan)
		info.appendChild(metaSpan)
		li.appendChild(img)
		li.appendChild(info)

		li.addEventListener('click', function () { focusPlaygroup(playgroup) })
		li.addEventListener('keydown', function (event) {
			if (event.key === 'Enter' || event.key === ' ') {
				event.preventDefault()
				focusPlaygroup(playgroup)
			}
		})

		return li
	}

	function renderResults() {
		renderSummary()
		renderPagination()

		var pageStart = (currentPage - 1) * RESULTS_PAGE_SIZE
		var pagePlaygroups = visiblePlaygroups.slice(pageStart, pageStart + RESULTS_PAGE_SIZE)
		resultsList.replaceChildren.apply(resultsList, pagePlaygroups.map(buildResultItem))
		resultsList.scrollTop = 0
	}

	function renderError() {
		resultsSummary.textContent = 'Something went wrong loading groups. Please try again.'
		resultsList.replaceChildren()
		pagination.hidden = true
	}

	function focusPlaygroup(playgroup) {
		activePlaygroupId = playgroup.id
		var venue = findPreferredVenue(playgroup)
		var marker = markersByPlaygroupVenue[markerKey(playgroup.id, venue.id)]

		resultsList.querySelectorAll('li.active').forEach(function (el) {
			el.classList.remove('active')
		})
		var li = resultsList.querySelector('li[data-pg-id="' + playgroup.id + '"]')
		if (li) li.classList.add('active')

		if (MOBILE_MEDIA_QUERY.matches) {
			setSheetState('peek')
		}

		markers.zoomToShowLayer(marker, function () {
			marker.openPopup()
		})
	}

	function goToPage(page) {
		currentPage = Math.min(Math.max(1, page), pageCount())
		renderResults()
	}

	function buildRequestUrl() {
		var params = new URLSearchParams()
		var search = searchInput.value.trim()
		if (search) params.set('search', search)
		if (upcomingEventsInput.checked) params.set('upcoming_events', '1')
		var eventFormat = eventFormatInput.value
		if (eventFormat) params.set('event_format', eventFormat)

		var qs = params.toString()
		return qs ? window.FINDER_API_URL + '?' + qs : window.FINDER_API_URL
	}

	function fetchPlaygroups() {
		if (inFlightRequest) {
			inFlightRequest.abort()
		}
		var request = new AbortController()
		inFlightRequest = request

		fetch(buildRequestUrl(), { signal: request.signal })
			.then(function (response) {
				if (!response.ok) {
					throw new Error('Finder request failed: ' + response.status)
				}
				return response.json()
			})
			.then(function (data) {
				allPlaygroups = data.playgroups
				activePlaygroupId = null
				map.closePopup()
				renderMarkers()
				if (allPlaygroups.length > 0) {
					fitMapToAllPlaygroups()
				}
				refreshVisiblePlaygroups()
			})
			.catch(function (error) {
				if (error.name === 'AbortError') return
				renderError()
			})
			.finally(function () {
				if (inFlightRequest === request) {
					inFlightRequest = null
				}
			})
	}

	function debouncedFetch() {
		clearTimeout(debounceTimer)
		debounceTimer = setTimeout(fetchPlaygroups, 300)
	}

	function setSheetState(state) {
		panel.setAttribute('data-sheet-state', state)
		sheetHandle.setAttribute('aria-expanded', state === 'peek' ? 'false' : 'true')
	}

	function cycleSheetState() {
		var currentIndex = SHEET_STATES.indexOf(panel.getAttribute('data-sheet-state'))
		setSheetState(SHEET_STATES[(currentIndex + 1) % SHEET_STATES.length])
	}

	function enableSheetDragging() {
		var dragStartY = null
		var dragStartHeight = null
		var hasDragged = false

		sheetHandle.addEventListener('pointerdown', function (event) {
			if (!MOBILE_MEDIA_QUERY.matches) return
			dragStartY = event.clientY
			dragStartHeight = panel.getBoundingClientRect().height
			hasDragged = false
			sheetHandle.setPointerCapture(event.pointerId)
		})

		sheetHandle.addEventListener('pointermove', function (event) {
			if (dragStartY === null) return
			var deltaY = dragStartY - event.clientY
			if (Math.abs(deltaY) > 5) {
				hasDragged = true
				panel.classList.add('is-dragging')
				panel.style.height = Math.max(0, dragStartHeight + deltaY) + 'px'
			}
		})

		function endDrag() {
			if (dragStartY === null) return
			dragStartY = null
			if (!hasDragged) return

			var draggedHeight = panel.getBoundingClientRect().height
			panel.style.height = ''
			var nearestState = findNearestSheetState(draggedHeight)

			panel.style.height = draggedHeight + 'px'
			panel.getBoundingClientRect()
			panel.classList.remove('is-dragging')
			panel.style.height = ''
			setSheetState(nearestState)
		}

		sheetHandle.addEventListener('pointerup', endDrag)
		sheetHandle.addEventListener('pointercancel', endDrag)
		sheetHandle.addEventListener('click', function () {
			if (hasDragged) {
				hasDragged = false
				return
			}
			cycleSheetState()
		})
	}

	function findNearestSheetState(height) {
		var currentState = panel.getAttribute('data-sheet-state')
		var nearestState = currentState
		var nearestDistance = Infinity
		SHEET_STATES.forEach(function (state) {
			panel.setAttribute('data-sheet-state', state)
			var distance = Math.abs(panel.getBoundingClientRect().height - height)
			if (distance < nearestDistance) {
				nearestDistance = distance
				nearestState = state
			}
		})
		panel.setAttribute('data-sheet-state', currentState)
		return nearestState
	}

	function toggleMenu() {
		var isOpen = chrome.classList.toggle('is-menu-open')
		menuToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false')
	}

	searchInput.addEventListener('input', debouncedFetch)
	searchInput.addEventListener('focus', function () {
		if (MOBILE_MEDIA_QUERY.matches && panel.getAttribute('data-sheet-state') === 'peek') {
			setSheetState('half')
		}
	})
	upcomingEventsInput.addEventListener('change', fetchPlaygroups)
	eventFormatInput.addEventListener('change', fetchPlaygroups)
	previousPageButton.addEventListener('click', function () { goToPage(currentPage - 1) })
	nextPageButton.addEventListener('click', function () { goToPage(currentPage + 1) })
	menuToggle.addEventListener('click', toggleMenu)
	map.on('moveend', refreshVisiblePlaygroups)

	enableSheetDragging()
	fetchPlaygroups()
}())
