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

	var SOON_WINDOW_DAYS = 7
	var MARKER_PIN_PATH = 'M12 0C5.4 0 0 5.4 0 12c0 9 12 24 12 24s12-15 12-24C24 5.4 18.6 0 12 0z'
	var MARKER_STYLES = {
		primary: { fill: '#FFB400', width: 28, height: 40, dotRadius: 5 },
		secondary: { fill: '#888', width: 22, height: 32, dotRadius: 4 },
	}
	var CLUSTER_SIZES = [
		{ maxCount: 9, size: 34 },
		{ maxCount: 49, size: 40 },
		{ maxCount: Infinity, size: 48 },
	]

	var markers = L.markerClusterGroup({
		showCoverageOnHover: false,
		maxClusterRadius: 50,
		iconCreateFunction: buildClusterIcon,
	}).addTo(map)

	var cardHtmlByUrl = {}
	var POPUP_EDGE_GAP = 16

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

	function soonEventLabel(playgroup) {
		if (!playgroup.next_event) return null
		var days = window.FinderDates.daysUntil(playgroup.next_event.date)
		if (days < 0 || days >= SOON_WINDOW_DAYS) return null
		if (days === 0) return 'Today'
		if (days === 1) return 'Tomorrow'
		return window.FinderDates.parseLocalDate(playgroup.next_event.date).toLocaleDateString(undefined, { weekday: 'short' })
	}

	function buildMarkerIcon(isPrimary, soonLabel) {
		var style = isPrimary ? MARKER_STYLES.primary : MARKER_STYLES.secondary
		var classNames = ['finder-marker', isPrimary ? 'finder-marker-primary' : 'finder-marker-secondary']
		if (soonLabel) classNames.push('finder-marker-soon')
		return L.divIcon({
			className: classNames.join(' '),
			html: '<svg viewBox="0 0 24 36" width="' + style.width + '" height="' + style.height + '">' +
					'<path d="' + MARKER_PIN_PATH + '" fill="' + style.fill + '" stroke="#131313" stroke-width="1.5"/>' +
					'<circle cx="12" cy="11" r="' + style.dotRadius + '" fill="#131313"/>' +
				'</svg>' +
				(soonLabel ? '<span class="finder-marker-tag">' + escapeHtml(soonLabel) + '</span>' : ''),
			iconSize: [style.width, style.height],
			iconAnchor: [style.width / 2, style.height],
			popupAnchor: [0, -style.height + 4],
		})
	}

	function buildClusterIcon(cluster) {
		var count = cluster.getChildCount()
		var size = CLUSTER_SIZES.find(function (tier) { return count <= tier.maxCount }).size
		var hasSoonEvent = cluster.getAllChildMarkers().some(function (marker) {
			return marker.options.hasSoonEvent
		})
		return L.divIcon({
			className: 'finder-cluster' + (hasSoonEvent ? ' finder-cluster-soon' : ''),
			html: '<span>' + count + '</span>',
			iconSize: [size, size],
		})
	}

	function buildPopupShell(playgroup, venue) {
		var groupHasPrimaryVenue = playgroup.venues.some(function (candidate) { return candidate.is_primary })
		var secondaryLabel = groupHasPrimaryVenue && !venue.is_primary ? ' (Secondary)' : ''
		return '<div class="finder-popup">' +
			'<div class="finder-popup-venue">' + escapeHtml(venue.name) + secondaryLabel + '</div>' +
			'<div class="finder-popup-card" aria-live="polite" data-card-url="' + escapeHtml(playgroup.card_url) + '">' +
				(cardHtmlByUrl[playgroup.card_url] || '<div class="finder-popup-loading">Loading ' + escapeHtml(playgroup.name) + '…</div>') +
			'</div>' +
		'</div>'
	}

	function popupPaddingTopLeft() {
		var mapRect = map.getContainer().getBoundingClientRect()
		var chromeBottom = chrome.getBoundingClientRect().bottom - mapRect.top
		if (MOBILE_MEDIA_QUERY.matches) {
			return [POPUP_EDGE_GAP, chromeBottom + POPUP_EDGE_GAP]
		}
		var panelRight = panel.getBoundingClientRect().right - mapRect.left
		return [panelRight + POPUP_EDGE_GAP, chromeBottom + POPUP_EDGE_GAP]
	}

	function keepPopupClearOfOverlays() {
		closeMenu()
		if (MOBILE_MEDIA_QUERY.matches) {
			setSheetState('peek')
		}
	}

	function bindPopupClearOfOverlays(marker, buildContent) {
		marker.bindPopup(buildContent, { minWidth: 260, maxWidth: 300 })
		Object.defineProperty(marker.getPopup().options, 'autoPanPaddingTopLeft', {
			get: popupPaddingTopLeft,
		})
	}

	function loadPopupCard(event) {
		var cardContainer = event.popup.getElement().querySelector('.finder-popup-card')
		var cardUrl = cardContainer.getAttribute('data-card-url')
		if (cardHtmlByUrl[cardUrl]) return

		fetch(cardUrl)
			.then(function (response) {
				if (!response.ok) throw new Error('Card request failed: ' + response.status)
				return response.text()
			})
			.then(function (html) {
				cardContainer.innerHTML = html
				window.FinderDates.relabelRelativeEventDays(cardContainer)
				cardHtmlByUrl[cardUrl] = cardContainer.innerHTML
				event.popup.update()
			})
			.catch(function () {
				cardContainer.innerHTML = '<div class="finder-popup-loading">Couldn\u2019t load this group.</div>'
			})
	}

	function renderMarkers() {
		markers.clearLayers()
		markersByPlaygroupVenue = {}
		var newMarkers = []
		allPlaygroups.forEach(function (playgroup) {
			var soonLabel = soonEventLabel(playgroup)
			playgroup.venues.forEach(function (venue) {
				var marker = L.marker([venue.latitude, venue.longitude], {
					icon: buildMarkerIcon(venue.is_primary, soonLabel),
					hasSoonEvent: !!soonLabel,
				})
				bindPopupClearOfOverlays(marker, function () { return buildPopupShell(playgroup, venue) })
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

	function closeMenu() {
		chrome.classList.remove('is-menu-open')
		menuToggle.setAttribute('aria-expanded', 'false')
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
	map.on('popupopen', keepPopupClearOfOverlays)
	map.on('popupopen', loadPopupCard)
	map.on('click', closeMenu)
	panel.addEventListener('pointerdown', closeMenu)

	enableSheetDragging()
	fetchPlaygroups()
}())
