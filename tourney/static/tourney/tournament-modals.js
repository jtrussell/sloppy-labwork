function truncateName(name, maxLength = 25) {
  if (!name || name.length <= maxLength) return name
  return name.substring(0, maxLength - 1) + '…'
}

function openAddMatchModal() {
  const modal = document.getElementById('addMatchModal')
  const form = document.getElementById('addMatchForm')
  const playerOneSelect = document.getElementById('addMatchPlayerOne')
  const playerTwoSelect = document.getElementById('addMatchPlayerTwo')
  const addMatchUrl = modal.dataset.addMatchUrl
  const unmatchedPlayers = JSON.parse(modal.dataset.unmatchedPlayers || '[]')
  const isAdmin = modal.dataset.isAdmin === 'true'
  const currentUserId = parseInt(modal.dataset.currentUserId)

  form.setAttribute('hx-post', addMatchUrl)
  htmx.process(form)

  playerOneSelect.innerHTML = '<option value="">Select Player One</option>'

  let currentUserStagePlayerId = null

  unmatchedPlayers.forEach((player) => {
    const option = new Option(truncateName(player.name), player.id)
    option.title = player.name

    if (player.userId === currentUserId) {
      currentUserStagePlayerId = player.id
    }

    playerOneSelect.appendChild(option)
  })

  if (!isAdmin && currentUserStagePlayerId) {
    playerOneSelect.value = currentUserStagePlayerId
    playerOneSelect.disabled = true
  }

  populatePlayerTwoOptions(unmatchedPlayers, playerOneSelect.value)
  playerOneSelect.onchange = () =>
    populatePlayerTwoOptions(unmatchedPlayers, playerOneSelect.value)

  modal.showModal()
}

function populatePlayerTwoOptions(unmatchedPlayers, playerOneId) {
  const playerTwoSelect = document.getElementById('addMatchPlayerTwo')
  const playerOne = unmatchedPlayers.find(
    (player) => String(player.id) === String(playerOneId),
  )

  playerTwoSelect.innerHTML =
    '<option value="">Select Player Two (Bye)</option>'

  unmatchedPlayers
    .filter((player) => !playerOne || player.podId === playerOne.podId)
    .filter((player) => !playerOne || player.id !== playerOne.id)
    .forEach((player) => {
      const option = new Option(truncateName(player.name), player.id)
      option.title = player.name
      playerTwoSelect.appendChild(option)
    })
}

function closeAddMatchModal() {
  const modal = document.getElementById('addMatchModal')
  if (modal && modal.open) {
    modal.close()
  }
}

document.addEventListener('close', function (e) {
  if (e.target.id === 'addMatchModal') {
    const playerOneSelect = document.getElementById('addMatchPlayerOne')
    if (playerOneSelect) {
      playerOneSelect.disabled = false
    }
  }
}, true)

document.addEventListener('htmx:afterRequest', function (e) {
  if (
    e.detail.elt &&
    e.detail.elt.id === 'addMatchForm' &&
    e.detail.successful
  ) {
    closeAddMatchModal()
  }
})
