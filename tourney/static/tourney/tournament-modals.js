function truncateName(name, maxLength = 25) {
  if (!name || name.length <= maxLength) return name
  return name.substring(0, maxLength - 1) + '…'
}

function suggestWinnerFromScores(
  scoreOneInput,
  scoreTwoInput,
  winnerSelect,
  playerOneValue,
  playerTwoValue,
) {
  if (scoreOneInput.value === '' || scoreTwoInput.value === '') return
  if (winnerSelect.selectedIndex !== 0) return

  const scoreOne = parseInt(scoreOneInput.value, 10)
  const scoreTwo = parseInt(scoreTwoInput.value, 10)

  if (scoreOne > scoreTwo) {
    winnerSelect.value = playerOneValue
  } else if (scoreTwo > scoreOne) {
    winnerSelect.value = playerTwoValue
  }
}

function openMatchModal(button) {
  const modal = document.getElementById('matchModal')
  const form = document.getElementById('matchForm')
  const title = document.getElementById('modalTitle')
  const winnerSelect = document.getElementById('matchWinner')
  const deleteBtn = document.getElementById('deleteMatchBtn')

  const matchId = button.dataset.matchId
  const updateAction = button.dataset.updateAction
  const deleteAction = button.dataset.deleteAction
  const resetAction = button.dataset.resetAction
  const playerOne = button.dataset.matchPlayerOne
  const playerOneId = button.dataset.matchPlayerOneId
  const playerTwo = button.dataset.matchPlayerTwo
  const playerTwoId = button.dataset.matchPlayerTwoId
  const hasResult = button.dataset.matchHasResult === 'true'
  const currentWinnerId = button.dataset.matchWinnerId
  const isBye = button.dataset.matchIsBye === 'true'

  window.currentDeleteAction = deleteAction
  window.currentResetAction = resetAction
  window.currentMatchPlayerOne = playerOne
  window.currentMatchPlayerTwo = playerTwo

  if (isBye) {
    form.setAttribute('onsubmit', 'return false;')
    title.textContent = 'Bye Match'
  } else {
    form.setAttribute('hx-post', updateAction)
    htmx.process(form)
    title.textContent = hasResult
      ? 'Update Match Result'
      : 'Report Match Result'
  }

  const resetBtn = document.getElementById('resetMatchBtn')
  if (deleteBtn && button.dataset.isAdmin === 'true') {
    deleteBtn.style.display = 'inline-block'
  }

  if (resetBtn && button.dataset.isAdmin === 'true') {
    if (hasResult && !isBye) {
      resetBtn.style.display = 'inline-block'
    } else {
      resetBtn.style.display = 'none'
    }
  }

  const winnerDiv = winnerSelect.closest('div')
  const scoreInputs = document.getElementById('scoreInputs')
  const submitButton = form.querySelector('button[type="submit"]')

  if (isBye) {
    if (winnerDiv) winnerDiv.style.display = 'none'
    if (scoreInputs) scoreInputs.style.display = 'none'
    if (submitButton) submitButton.style.display = 'none'
  } else {
    if (winnerDiv) winnerDiv.style.display = 'block'
    if (submitButton) submitButton.style.display = 'inline-block'

    winnerSelect.innerHTML = '<option value="">Select Winner</option>'

    if (playerOne) {
      const option1 = new Option(truncateName(playerOne), playerOneId)
      option1.title = playerOne
      if (currentWinnerId === playerOneId) option1.selected = true
      winnerSelect.appendChild(option1)
    }

    if (playerTwo) {
      const option2 = new Option(truncateName(playerTwo), playerTwoId)
      option2.title = playerTwo
      if (currentWinnerId === playerTwoId) option2.selected = true
      winnerSelect.appendChild(option2)
    }

    const stageAllowTies = button.dataset.stageAllowTies === 'true'
    if (stageAllowTies) {
      const tieOption = new Option('Tie', '')
      if (!currentWinnerId && hasResult) tieOption.selected = true
      winnerSelect.appendChild(tieOption)
    }
  }

  if (!isBye) {
    const stageScoreReporting = parseInt(button.dataset.stageScoreReporting)
    const scoreInputsSection = document.getElementById('scoreInputs')

    if (stageScoreReporting === 0) {
      if (scoreInputsSection) scoreInputsSection.style.display = 'none'
    } else {
      if (scoreInputsSection) scoreInputsSection.style.display = 'block'

      const playerOneScoreLabel = document.getElementById('playerOneScoreLabel')
      const playerTwoScoreLabel = document.getElementById('playerTwoScoreLabel')
      const playerOneScoreInput = document.getElementById('playerOneScore')
      const playerTwoScoreInput = document.getElementById('playerTwoScore')

      const playerLabelSuffix = stageScoreReporting === 2 ? '*' : ''
      if (playerOneScoreLabel && playerOne) {
        playerOneScoreLabel.textContent =
          truncateName(playerOne) + playerLabelSuffix
        playerOneScoreLabel.title = playerOne
      }
      if (playerTwoScoreLabel && playerTwo) {
        playerTwoScoreLabel.textContent =
          truncateName(playerTwo) + playerLabelSuffix
        playerTwoScoreLabel.title = playerTwo
      } else if (playerTwoScoreLabel) {
        playerTwoScoreLabel.textContent = 'Player Two'
      }

      if (stageScoreReporting === 2) {
        if (playerOneScoreInput) playerOneScoreInput.required = true
        if (playerTwoScoreInput) playerTwoScoreInput.required = true
      } else {
        if (playerOneScoreInput) playerOneScoreInput.required = false
        if (playerTwoScoreInput) playerTwoScoreInput.required = false
      }

      const playerOneScore = button.dataset.matchPlayerOneScore || ''
      const playerTwoScore = button.dataset.matchPlayerTwoScore || ''

      if (playerOneScoreInput) playerOneScoreInput.value = playerOneScore
      if (playerTwoScoreInput) playerTwoScoreInput.value = playerTwoScore

      const onScoreInput = () =>
        suggestWinnerFromScores(
          playerOneScoreInput,
          playerTwoScoreInput,
          winnerSelect,
          playerOneId,
          playerTwoId,
        )
      playerOneScoreInput.oninput = onScoreInput
      playerTwoScoreInput.oninput = onScoreInput
    }
  }

  modal.classList.add('modal--active')
}

function closeMatchModal() {
  const modal = document.getElementById('matchModal')
  modal.classList.remove('modal--active')
}

function resetMatch() {
  if (!window.currentResetAction) return

  const resetBtn = document.getElementById('resetMatchBtn')
  const playerNames = window.currentMatchPlayerTwo
    ? `${window.currentMatchPlayerOne} and ${window.currentMatchPlayerTwo}`
    : window.currentMatchPlayerOne

  resetBtn.setAttribute('hx-post', window.currentResetAction)
  resetBtn.setAttribute(
    'hx-confirm',
    `Are you sure you want to reset this match between ${playerNames}?`,
  )

  htmx.process(resetBtn)
  resetBtn.click()
}

function deleteMatch() {
  if (!window.currentDeleteAction) return

  const deleteBtn = document.getElementById('deleteMatchBtn')
  const playerNames = window.currentMatchPlayerTwo
    ? `${window.currentMatchPlayerOne} and ${window.currentMatchPlayerTwo}`
    : window.currentMatchPlayerOne

  deleteBtn.setAttribute('hx-post', window.currentDeleteAction)
  deleteBtn.setAttribute(
    'hx-confirm',
    `Are you sure you want to delete this match between ${playerNames}? Our lawyers insist that we ask.`,
  )

  htmx.process(deleteBtn)
  deleteBtn.click()
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
  playerTwoSelect.innerHTML =
    '<option value="">Select Player Two (Bye)</option>'

  let currentUserStagePlayerId = null

  unmatchedPlayers.forEach((player) => {
    const option1 = new Option(truncateName(player.name), player.id)
    const option2 = new Option(truncateName(player.name), player.id)
    option1.title = player.name
    option2.title = player.name

    if (player.userId === currentUserId) {
      currentUserStagePlayerId = player.id
    }

    playerOneSelect.appendChild(option1)
    playerTwoSelect.appendChild(option2)
  })

  if (!isAdmin && currentUserStagePlayerId) {
    playerOneSelect.value = currentUserStagePlayerId
    playerOneSelect.disabled = true
  }

  modal.classList.add('modal--active')
}

function closeAddMatchModal() {
  const modal = document.getElementById('addMatchModal')
  const playerOneSelect = document.getElementById('addMatchPlayerOne')

  if (playerOneSelect) {
    playerOneSelect.disabled = false
  }

  modal.classList.remove('modal--active')
}

function openPlayerMatchReportModal() {
  const modal = document.getElementById('playerMatchReportModal')
  const form = document.getElementById('playerMatchReportForm')
  const opponentSelect = document.getElementById('playerMatchOpponent')
  const winnerSelect = document.getElementById('playerMatchWinner')
  const scoreInputsSection = document.getElementById('playerScoreInputs')

  const reportUrl = modal.dataset.reportUrl
  const unmatchedPlayers = JSON.parse(modal.dataset.unmatchedPlayers || '[]')
  const currentUserId = parseInt(modal.dataset.currentUserId)
  const stageAllowTies = modal.dataset.stageAllowTies === 'true'
  const stageScoreReporting = parseInt(modal.dataset.stageScoreReporting || '0')

  form.setAttribute('hx-post', reportUrl)
  htmx.process(form)

  opponentSelect.innerHTML = '<option value="">Select your opponent</option>'

  unmatchedPlayers.forEach((player) => {
    if (player.userId !== currentUserId) {
      const option = new Option(truncateName(player.name), player.id)
      option.title = player.name
      opponentSelect.appendChild(option)
    }
  })

  winnerSelect.innerHTML = '<option value="">Select winner</option>'
  winnerSelect.innerHTML += '<option value="me">I won</option>'
  winnerSelect.innerHTML += '<option value="them">They won</option>'

  if (stageAllowTies) {
    winnerSelect.innerHTML += '<option value="tie">We tied</option>'
  }

  if (stageScoreReporting > 0) {
    scoreInputsSection.style.display = 'block'
    const myScoreInput = document.getElementById('playerMyScore')
    const theirScoreInput = document.getElementById('playerTheirScore')

    if (stageScoreReporting === 2) {
      myScoreInput.required = true
      theirScoreInput.required = true
    } else {
      myScoreInput.required = false
      theirScoreInput.required = false
    }

    const onScoreInput = () =>
      suggestWinnerFromScores(
        myScoreInput,
        theirScoreInput,
        winnerSelect,
        'me',
        'them',
      )
    myScoreInput.oninput = onScoreInput
    theirScoreInput.oninput = onScoreInput
  } else {
    scoreInputsSection.style.display = 'none'
  }

  modal.classList.add('modal--active')
}

function closePlayerMatchReportModal() {
  const modal = document.getElementById('playerMatchReportModal')
  modal.classList.remove('modal--active')
}

document.addEventListener('click', function (e) {
  const matchModal = document.getElementById('matchModal')
  if (e.target === matchModal) {
    closeMatchModal()
  }

  const addMatchModal = document.getElementById('addMatchModal')
  if (e.target === addMatchModal) {
    closeAddMatchModal()
  }

  const playerMatchReportModal = document.getElementById(
    'playerMatchReportModal',
  )
  if (e.target === playerMatchReportModal) {
    closePlayerMatchReportModal()
  }
})

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    closeMatchModal()
    closeAddMatchModal()
    closePlayerMatchReportModal()
  }
})

document.addEventListener('htmx:afterRequest', function (e) {
  if (
    e.detail.elt &&
    e.detail.elt.id === 'addMatchForm' &&
    e.detail.successful
  ) {
    closeAddMatchModal()
  }
  if (
    e.detail.elt &&
    e.detail.elt.id === 'playerMatchReportForm' &&
    e.detail.successful
  ) {
    closePlayerMatchReportModal()
  }
})
