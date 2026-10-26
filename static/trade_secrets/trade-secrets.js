(function () {
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
    const noun = form.dataset.pickNoun || 'deck'

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
      status.textContent = `Tap a selected ${noun} again to lock in.`
    } else if (selectedCount === 0) {
      status.textContent = requiredCount === 1
        ? `Tap a ${noun} to select it, tap again to lock in.`
        : `Tap ${requiredCount} ${noun}s to select them.`
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

  function centerCurrentRailStep(rail) {
    const current = rail.querySelector('.is-current')
    if (current) {
      rail.scrollLeft = current.offsetLeft - (rail.clientWidth - current.clientWidth) / 2
    }
  }

  function initialize(scope) {
    scope.querySelectorAll('.step-rail').forEach(centerCurrentRailStep)
    scope.querySelectorAll('#ts-board').forEach(markFreshReveal)
    scope.querySelectorAll('.ts-pick-form').forEach(refreshPickForm)
  }

  document.addEventListener('click', function (event) {
    const pickInput = event.target.closest('.ts-pick-input')
    if (pickInput && event.target === pickInput) {
      handlePickTap(pickInput, event)
    }
  })

  document.addEventListener('focusin', function (event) {
    if (event.target.matches('[data-select-on-focus]')) {
      event.target.select()
    }
  })

  document.addEventListener('htmx:afterSettle', function () {
    initialize(document)
  })

  initialize(document)
})()
