(function () {
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

	var markers = L.layerGroup().addTo(map)
	var allPlaygroups = []
	var debounceTimer = null

	var searchInput = document.getElementById('finder-search-input')
	var minMembersInput = document.getElementById('finder-min-members')
	var maxMembersInput = document.getElementById('finder-max-members')
	var resultsList = document.getElementById('finder-results')

	function buildPopupHtml(playgroup, venue) {
		var primaryLabel = venue.is_primary ? ' (Primary)' : ''
		return '<div class="finder-popup">' +
			'<div class="finder-popup-header">' +
				'<img class="finder-popup-logo" src="' + escapeHtml(playgroup.logo_src) + '" alt="" />' +
				'<div class="finder-popup-name"><a href="' + playgroup.url + '">' + escapeHtml(playgroup.name) + '</a></div>' +
			'</div>' +
			'<div class="finder-popup-venue">' + escapeHtml(venue.name) + primaryLabel + '</div>' +
			'<div class="finder-popup-meta">' +
				(venue.city ? escapeHtml(venue.city) : '') +
				(venue.city && venue.country ? ', ' : '') +
				(venue.country ? escapeHtml(venue.country) : '') +
			'</div>' +
			'<div class="finder-popup-meta">' + playgroup.member_count + ' member' + (playgroup.member_count !== 1 ? 's' : '') + '</div>' +
		'</div>'
	}

	function escapeHtml(str) {
		var div = document.createElement('div')
		div.textContent = str
		return div.innerHTML
	}

	function renderMarkers(playgroups) {
		markers.clearLayers()
		playgroups.forEach(function (pg) {
			pg.venues.forEach(function (venue) {
				var icon = venue.is_primary ? primaryIcon : secondaryIcon
				var marker = L.marker([venue.latitude, venue.longitude], { icon: icon })
				marker.bindPopup(buildPopupHtml(pg, venue))
				markers.addLayer(marker)
			})
		})
	}

	function renderResults(playgroups) {
		resultsList.innerHTML = ''

		if (playgroups.length === 0) {
			resultsList.innerHTML = '<li class="finder-no-results">No playgroups found</li>'
			return
		}

		playgroups.forEach(function (pg) {
			var li = document.createElement('li')
			li.setAttribute('data-pg-id', pg.id)

			var img = document.createElement('img')
			img.src = pg.logo_src
			img.alt = ''
			img.className = 'finder-result-logo'

			var info = document.createElement('div')
			info.className = 'finder-result-info'

			var nameSpan = document.createElement('span')
			nameSpan.className = 'finder-result-name'
			nameSpan.textContent = pg.name

			var metaSpan = document.createElement('span')
			metaSpan.className = 'finder-result-meta'
			var metaParts = []
			metaParts.push(pg.member_count + ' member' + (pg.member_count !== 1 ? 's' : ''))
			if (pg.type) {
				metaParts.push(pg.type)
			}
			metaSpan.textContent = metaParts.join(' \u2022 ')

			info.appendChild(nameSpan)
			info.appendChild(metaSpan)
			li.appendChild(img)
			li.appendChild(info)

			li.addEventListener('click', function () {
				map.setView([pg.primary_latitude, pg.primary_longitude], 13)

				document.querySelectorAll('.finder-results li.active').forEach(function (el) {
					el.classList.remove('active')
				})
				li.classList.add('active')

				markers.eachLayer(function (marker) {
					var latlng = marker.getLatLng()
					if (Math.abs(latlng.lat - pg.primary_latitude) < 0.0001 &&
						Math.abs(latlng.lng - pg.primary_longitude) < 0.0001) {
						marker.openPopup()
					}
				})
			})

			resultsList.appendChild(li)
		})
	}

	function fetchPlaygroups() {
		var params = new URLSearchParams()
		var search = searchInput.value.trim()
		if (search) params.set('search', search)
		var minMembers = minMembersInput.value.trim()
		if (minMembers) params.set('min_members', minMembers)
		var maxMembers = maxMembersInput.value.trim()
		if (maxMembers) params.set('max_members', maxMembers)

		var url = '/pmc/api/finder/'
		var qs = params.toString()
		if (qs) url += '?' + qs

		fetch(url)
			.then(function (response) { return response.json() })
			.then(function (data) {
				allPlaygroups = data.playgroups
				renderMarkers(allPlaygroups)
				renderResults(allPlaygroups)

				if (allPlaygroups.length > 0) {
					var bounds = []
					allPlaygroups.forEach(function (pg) {
						pg.venues.forEach(function (v) {
							bounds.push([v.latitude, v.longitude])
						})
					})
					if (bounds.length > 0) {
						map.fitBounds(bounds, { padding: [50, 50], maxZoom: 12 })
					}
				}
			})
	}

	function debouncedFetch() {
		clearTimeout(debounceTimer)
		debounceTimer = setTimeout(fetchPlaygroups, 300)
	}

	searchInput.addEventListener('input', debouncedFetch)
	minMembersInput.addEventListener('input', debouncedFetch)
	maxMembersInput.addEventListener('input', debouncedFetch)

	fetchPlaygroups()
}())
