const SCORE_REPORTING_DISABLED = 0
const SCORE_REPORTING_REQUIRED = 2

function getReportDialogElements() {
  return {
    modal: document.getElementById('matchModal'),
    form: document.getElementById('matchForm'),
    body: document.querySelector('#matchModal .report-dialog__body'),
    title: document.getElementById('modalTitle'),
    roundLabel: document.getElementById('reportRoundLabel'),
    feedback: document.getElementById('reportFeedback'),
    opponentField: document.getElementById('reportOpponentField'),
    opponentSelect: document.getElementById('reportOpponent'),
    outcome: document.getElementById('reportOutcome'),
    playerOneName: document.getElementById('reportPlayerOneName'),
    playerTwoName: document.getElementById('reportPlayerTwoName'),
    playerOneWinner: document.getElementById('reportWinnerPlayerOne'),
    playerTwoWinner: document.getElementById('reportWinnerPlayerTwo'),
    tieOption: document.getElementById('reportTieOption'),
    tieWinner: document.getElementById('reportWinnerTie'),
    playerOneScore: document.getElementById('reportPlayerOneScore'),
    playerTwoScore: document.getElementById('reportPlayerTwoScore'),
    byeNotice: document.getElementById('reportByeNotice'),
    submitButton: document.getElementById('reportSubmitButton'),
    adminMenu: document.getElementById('reportAdminMenu'),
    resetButton: document.getElementById('resetMatchBtn'),
  }
}

function setReportPlayerName(nameElement, name) {
  nameElement.textContent = name
  nameElement.title = name
}

function getWinnerOptions(elements) {
  return [elements.playerOneWinner, elements.playerTwoWinner, elements.tieWinner]
}

function configureWinnerOptions(
  elements,
  winnerValues,
  allowsTie,
  selectedWinnerValue,
  isDisabled = false,
) {
  elements.playerOneWinner.value = winnerValues.playerOne
  elements.playerTwoWinner.value = winnerValues.playerTwo
  elements.tieWinner.value = winnerValues.tie
  elements.tieOption.hidden = !allowsTie
  elements.playerOneWinner.disabled = isDisabled
  elements.playerTwoWinner.disabled = isDisabled
  elements.tieWinner.disabled = isDisabled || !allowsTie

  getWinnerOptions(elements).forEach((winnerOption) => {
    winnerOption.checked =
      !winnerOption.disabled &&
      selectedWinnerValue !== null &&
      winnerOption.value === selectedWinnerValue
  })
}

function suggestWinnerFromScores(elements) {
  const playerOneScore = elements.playerOneScore.value
  const playerTwoScore = elements.playerTwoScore.value
  if (playerOneScore === '' || playerTwoScore === '') return
  if (getWinnerOptions(elements).some((winnerOption) => winnerOption.checked)) return

  const scoreDifference = parseInt(playerOneScore, 10) - parseInt(playerTwoScore, 10)
  if (scoreDifference > 0) elements.playerOneWinner.checked = true
  if (scoreDifference < 0) elements.playerTwoWinner.checked = true
}

function configureScoreInputs(elements, scoreReporting, scoreFieldNames, scoreValues) {
  const showsScores = scoreReporting !== SCORE_REPORTING_DISABLED
  elements.form
    .querySelectorAll('[data-score-field]')
    .forEach((scoreField) => {
      scoreField.hidden = !showsScores
    })

  const scoreInputs = [elements.playerOneScore, elements.playerTwoScore]
  const playerNames = [elements.playerOneName.textContent, elements.playerTwoName.textContent]
  scoreInputs.forEach((scoreInput, index) => {
    scoreInput.name = scoreFieldNames[index]
    scoreInput.setAttribute('aria-label', `Score for ${playerNames[index] || 'player'}`)
    scoreInput.disabled = !showsScores
    scoreInput.required = scoreReporting === SCORE_REPORTING_REQUIRED
    scoreInput.value = scoreValues[index] || ''
    scoreInput.oninput = () => suggestWinnerFromScores(elements)
  })
}

function resetResultFormFields(form, isHidden) {
  const resultFormSection = form.querySelector('[data-result-form]')
  if (!resultFormSection) return
  resultFormSection.hidden = isHidden
  if (resultFormSection.tagName === 'DETAILS') resultFormSection.open = false
  resultFormSection
    .querySelectorAll('input, select, textarea')
    .forEach((field) => {
      field.disabled = isHidden
      if (field.type === 'checkbox') {
        field.checked = false
        field.dispatchEvent(new Event('change', { bubbles: true }))
      } else {
        field.value = ''
        field.dispatchEvent(new Event('input', { bubbles: true }))
      }
    })
  resultFormSection
    .querySelectorAll('.ghostform-errors')
    .forEach((errorMessage) => errorMessage.remove())
}

function configureAdminMenu(elements, isAdmin, canReset) {
  if (!elements.adminMenu) return
  elements.adminMenu.hidden = !isAdmin
  elements.adminMenu.open = false
  elements.resetButton.hidden = !canReset
}

function configureOpponentField(elements, opponents) {
  const isChoosingOpponent = opponents !== null
  elements.opponentField.hidden = !isChoosingOpponent
  elements.opponentSelect.disabled = !isChoosingOpponent
  elements.opponentSelect.required = isChoosingOpponent
  elements.opponentSelect.onchange = null
  if (!isChoosingOpponent) return

  elements.opponentSelect.innerHTML = '<option value="">Select your opponent</option>'
  opponents.forEach((opponent) => {
    const option = new Option(opponent.name, opponent.id)
    option.title = opponent.name
    elements.opponentSelect.appendChild(option)
  })
  elements.opponentSelect.onchange = () => {
    const selectedOpponent = elements.opponentSelect.selectedOptions[0]
    const opponentName = elements.opponentSelect.value ? selectedOpponent.title : 'Opponent'
    setReportPlayerName(elements.playerTwoName, opponentName)
    elements.playerTwoScore.setAttribute('aria-label', `Score for ${opponentName}`)
  }
}

function setReportAction(form, actionUrl) {
  form.setAttribute('hx-post', actionUrl)
  htmx.process(form)
}

let elementFocusedBeforeReportDialog = null

function getFocusableReportDialogElements(dialog) {
  return [...dialog.querySelectorAll(
    'button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.disabled && element.offsetParent !== null)
}

function showReportDialog(elements) {
  elementFocusedBeforeReportDialog = document.activeElement
  elements.feedback.innerHTML = ''
  elements.modal.classList.add('modal--active')
  document.body.classList.add('has-open-dialog')
  elements.body.scrollTop = 0
  elements.modal.querySelector('.report-dialog').focus()
}

function isReportDialogOpen() {
  const modal = document.getElementById('matchModal')
  return Boolean(modal && modal.classList.contains('modal--active'))
}

function openMatchModal(button) {
  const elements = getReportDialogElements()
  const isBye = button.dataset.matchIsBye === 'true'
  const hasResult = button.dataset.matchHasResult === 'true'
  const playerOne = button.dataset.matchPlayerOne
  const playerTwo = button.dataset.matchPlayerTwo || ''

  window.currentDeleteAction = button.dataset.deleteAction
  window.currentResetAction = button.dataset.resetAction
  window.currentMatchPlayerOne = playerOne
  window.currentMatchPlayerTwo = playerTwo

  setReportAction(elements.form, button.dataset.updateAction)
  elements.title.textContent = isBye
    ? 'Bye'
    : hasResult
      ? 'Update Match Result'
      : 'Report Match Result'
  elements.roundLabel.textContent = button.dataset.roundLabel || ''

  configureOpponentField(elements, null)
  setReportPlayerName(elements.playerOneName, playerOne)
  setReportPlayerName(elements.playerTwoName, playerTwo)
  elements.outcome.hidden = isBye
  elements.byeNotice.hidden = !isBye
  elements.byeNotice.textContent = `${playerOne} has a bye this round.`
  elements.submitButton.hidden = isBye

  configureWinnerOptions(
    elements,
    {
      playerOne: button.dataset.matchPlayerOneId,
      playerTwo: button.dataset.matchPlayerTwoId || '',
      tie: '',
    },
    button.dataset.stageAllowTies === 'true',
    hasResult && !isBye ? button.dataset.matchWinnerId || '' : null,
    isBye,
  )
  configureScoreInputs(
    elements,
    isBye ? SCORE_REPORTING_DISABLED : parseInt(button.dataset.stageScoreReporting, 10),
    ['player_one_score', 'player_two_score'],
    [button.dataset.matchPlayerOneScore, button.dataset.matchPlayerTwoScore],
  )
  resetResultFormFields(elements.form, isBye)
  configureAdminMenu(elements, button.dataset.isAdmin === 'true', hasResult && !isBye)

  showReportDialog(elements)
}

function openPlayerMatchReportModal() {
  const elements = getReportDialogElements()
  const modalData = elements.modal.dataset

  setReportAction(elements.form, modalData.playerReportUrl)
  elements.title.textContent = 'Report Match Result'
  elements.roundLabel.textContent = modalData.currentRoundLabel || ''

  configureOpponentField(elements, JSON.parse(modalData.opponents || '[]'))
  setReportPlayerName(elements.playerOneName, modalData.viewerName || 'You')
  setReportPlayerName(elements.playerTwoName, 'Opponent')
  elements.outcome.hidden = false
  elements.byeNotice.hidden = true
  elements.submitButton.hidden = false

  configureWinnerOptions(
    elements,
    { playerOne: 'me', playerTwo: 'them', tie: 'tie' },
    modalData.stageAllowTies === 'true',
    null,
  )
  configureScoreInputs(
    elements,
    parseInt(modalData.stageScoreReporting || '0', 10),
    ['my_score', 'their_score'],
    ['', ''],
  )
  resetResultFormFields(elements.form, false)
  configureAdminMenu(elements, false, false)

  showReportDialog(elements)
}

function closeMatchModal() {
  if (!isReportDialogOpen()) return
  document.getElementById('matchModal').classList.remove('modal--active')
  document.body.classList.remove('has-open-dialog')
  if (elementFocusedBeforeReportDialog) elementFocusedBeforeReportDialog.focus()
  elementFocusedBeforeReportDialog = null
}

function confirmMatchAction(button, actionUrl, confirmationMessage) {
  button.setAttribute('hx-post', actionUrl)
  button.setAttribute('hx-confirm', confirmationMessage)
  htmx.process(button)
  button.click()
}

function getCurrentMatchPlayerNames() {
  return window.currentMatchPlayerTwo
    ? `${window.currentMatchPlayerOne} and ${window.currentMatchPlayerTwo}`
    : window.currentMatchPlayerOne
}

function resetMatch() {
  if (!window.currentResetAction) return
  confirmMatchAction(
    document.getElementById('resetMatchBtn'),
    window.currentResetAction,
    `Are you sure you want to reset this match between ${getCurrentMatchPlayerNames()}?`,
  )
}

function deleteMatch() {
  if (!window.currentDeleteAction) return
  confirmMatchAction(
    document.getElementById('deleteMatchBtn'),
    window.currentDeleteAction,
    `Are you sure you want to delete this match between ${getCurrentMatchPlayerNames()}? Our lawyers insist that we ask.`,
  )
}

let didPressStartOnReportBackdrop = false

function closeAdminMenuWhenPressedOutside(event) {
  const adminMenu = document.getElementById('reportAdminMenu')
  if (adminMenu && adminMenu.open && !adminMenu.contains(event.target)) adminMenu.open = false
}

document.addEventListener('pointerdown', (event) => {
  didPressStartOnReportBackdrop = event.target === document.getElementById('matchModal')
  closeAdminMenuWhenPressedOutside(event)
})

document.addEventListener('click', (event) => {
  const pressedAndReleasedOnBackdrop =
    didPressStartOnReportBackdrop && event.target === document.getElementById('matchModal')
  didPressStartOnReportBackdrop = false
  if (pressedAndReleasedOnBackdrop) closeMatchModal()
})

function keepFocusInReportDialog(event) {
  const dialog = document.querySelector('#matchModal .report-dialog')
  const focusableElements = getFocusableReportDialogElements(dialog)
  if (focusableElements.length === 0) return
  const firstFocusableElement = focusableElements[0]
  const lastFocusableElement = focusableElements[focusableElements.length - 1]
  const isLeavingStart =
    event.shiftKey &&
    (document.activeElement === firstFocusableElement || document.activeElement === dialog)
  const isLeavingEnd = !event.shiftKey && document.activeElement === lastFocusableElement
  if (isLeavingStart) {
    event.preventDefault()
    lastFocusableElement.focus()
  } else if (isLeavingEnd) {
    event.preventDefault()
    firstFocusableElement.focus()
  }
}

document.addEventListener('keydown', (event) => {
  if (!isReportDialogOpen()) return
  if (event.key === 'Tab') {
    keepFocusInReportDialog(event)
    return
  }
  if (event.key !== 'Escape') return
  const adminMenu = document.getElementById('reportAdminMenu')
  if (adminMenu && adminMenu.open) {
    adminMenu.open = false
    return
  }
  closeMatchModal()
})

function revealResultFormErrors() {
  const resultFormSection = document.querySelector('#matchModal [data-result-form]')
  if (!resultFormSection) return
  const hasErrors = resultFormSection.querySelector('.ghostform-errors') !== null
  if (hasErrors && resultFormSection.tagName === 'DETAILS') resultFormSection.open = true
}

document.addEventListener('htmx:afterSwap', (event) => {
  if (event.detail.target && event.detail.target.id === 'reportFeedback') {
    const reportDialogBody = document.querySelector('#matchModal .report-dialog__body')
    if (reportDialogBody) reportDialogBody.scrollTop = 0
    revealResultFormErrors()
  }
})
