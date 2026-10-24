(function () {
  const COPIED_LABEL_DURATION_MS = 2000
  const selectionOrderByForm = new WeakMap()

  function checkedPickInputs(form) {
    return Array.from(form.querySelectorAll('.ts-pick-input:checked'))
  }

  function selectionOrder(form) {
    if (!selectionOrderByForm.has(form)) {
      selectionOrderByForm.set(form, checkedPickInputs(form))
    }
    return selectionOrderByForm.get(form)
  }

  function lockedValues(form) {
    return Array.from(form.querySelectorAll('.ts-pick-input[data-locked]'))
      .map(input => input.value)
      .sort()
  }

  function checkedValues(form) {
    return checkedPickInputs(form).map(input => input.value).sort()
  }

  function matchesLockedPick(form) {
    const locked = lockedValues(form)
    return locked.length > 0 && locked.join(',') === checkedValues(form).join(',')
  }

  function refreshPickForm(form) {
    const requiredCount = Number(form.dataset.pickCount)
    const selectedCount = checkedPickInputs(form).length
    const status = form.querySelector('[data-pick-status]')
    const submitButton = form.querySelector('[data-pick-submit]')

    form.querySelectorAll('.ts-pick-input').forEach(input => {
      input.closest('.ts-deck').classList.toggle('is-selected', input.checked)
    })

    if (submitButton) {
      submitButton.disabled = selectedCount !== requiredCount || matchesLockedPick(form)
    }
    if (!status) {
      return
    }
    if (matchesLockedPick(form)) {
      status.textContent = `Locked in. You can change until ${form.dataset.opponent} locks in.`
    } else if (selectedCount === requiredCount) {
      status.textContent = 'Tap a selected deck again to lock in.'
    } else if (selectedCount === 0) {
      status.textContent = requiredCount === 1
        ? 'Tap a deck to select it, tap again to lock in.'
        : `Tap ${requiredCount} decks to select them.`
    } else {
      status.textContent = `${selectedCount} of ${requiredCount} selected`
    }
  }

  function handlePickTap(input, event) {
    const form = input.closest('.ts-pick-form')
    const requiredCount = Number(form.dataset.pickCount)
    const order = selectionOrder(form)

    if (input.checked) {
      if (!order.includes(input)) {
        order.push(input)
      }
      while (order.length > requiredCount) {
        order.shift().checked = false
      }
    } else if (checkedPickInputs(form).length + 1 === requiredCount) {
      event.preventDefault()
      input.checked = true
      if (!matchesLockedPick(form)) {
        input.closest('.ts-deck').classList.add('is-confirming')
        form.requestSubmit()
      }
    } else {
      order.splice(order.indexOf(input), 1)
    }
    refreshPickForm(form)
  }

  function flashCopied(button) {
    const label = button.querySelector('[data-copy-label]') || button
    const originalText = label.dataset.originalText || label.textContent
    label.dataset.originalText = originalText
    label.textContent = 'Copied!'
    setTimeout(function () {
      label.textContent = originalText
    }, COPIED_LABEL_DURATION_MS)
  }

  function revealCopySource(button) {
    const source = button.dataset.copyFrom && document.querySelector(button.dataset.copyFrom)
    if (source) {
      source.hidden = false
      source.select()
    }
  }

  function handleCopy(button) {
    const source = button.dataset.copyFrom && document.querySelector(button.dataset.copyFrom)
    const text = source ? source.value : button.dataset.copyText
    if (!navigator.clipboard) {
      revealCopySource(button)
      return
    }
    navigator.clipboard.writeText(text)
      .then(() => flashCopied(button))
      .catch(() => revealCopySource(button))
  }

  function handleShare(button) {
    navigator.share({ title: button.dataset.shareTitle, url: button.dataset.shareUrl }).catch(() => {})
  }

  function closeDialog() {
    const dialog = document.getElementById('ts-dialog')
    if (dialog && dialog.open) {
      dialog.close()
    }
  }

  function readSeenRevealCount(key) {
    try {
      return Number(window.localStorage.getItem(key))
    } catch (error) {
      return NaN
    }
  }

  function storeSeenRevealCount(key, count) {
    try {
      window.localStorage.setItem(key, String(count))
    } catch (error) {
      return
    }
  }

  function markFreshReveal(board) {
    const reveal = board.querySelector('.ts-reveal')
    const key = `ts:${board.dataset.sessionCode}:seen`
    const revealedCount = Number(board.dataset.revealedCount)
    if (reveal && !(readSeenRevealCount(key) >= revealedCount)) {
      reveal.classList.add('is-fresh')
    }
    storeSeenRevealCount(key, revealedCount)
  }

  function initialize(scope) {
    scope.querySelectorAll('#ts-board').forEach(markFreshReveal)
    scope.querySelectorAll('.ts-pick-form').forEach(refreshPickForm)
    if (navigator.share) {
      scope.querySelectorAll('[data-share-url]').forEach(button => { button.hidden = false })
    }
  }

  document.addEventListener('click', function (event) {
    const pickInput = event.target.closest('.ts-pick-input')
    if (pickInput && event.target === pickInput) {
      handlePickTap(pickInput, event)
      return
    }
    const copyButton = event.target.closest('[data-copy-text], [data-copy-from]')
    if (copyButton) {
      handleCopy(copyButton)
      return
    }
    const shareButton = event.target.closest('[data-share-url]')
    if (shareButton && navigator.share) {
      handleShare(shareButton)
      return
    }
    if (event.target.closest('[data-close-dialog]') && event.target.closest('#ts-dialog')) {
      event.preventDefault()
      closeDialog()
      return
    }
    if (event.target.id === 'ts-dialog') {
      closeDialog()
    }
  })

  document.addEventListener('focusin', function (event) {
    if (event.target.matches('[data-select-on-focus]')) {
      event.target.select()
    }
  })

  document.addEventListener('htmx:afterSwap', function (event) {
    const target = event.detail.target
    if (target.id === 'ts-dialog') {
      if (!target.open) {
        target.showModal()
      }
      return
    }
    if (event.detail.requestConfig && event.detail.requestConfig.elt.closest('#ts-dialog')) {
      closeDialog()
    }
  })

  document.addEventListener('htmx:afterSettle', function () {
    initialize(document)
  })

  initialize(document)
})()
