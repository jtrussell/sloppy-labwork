(function () {
  const DIALOG_SELECTOR = 'dialog.dialog'
  const CONFIRM_DIALOG_ID = 'confirm-dialog'
  const CONFIRMED_RETURN_VALUE = 'confirm'
  const dialogsToCloseAfterSwap = new WeakMap()
  let pointerPressStartedOnBackdrop = false

  function isDialogBackdrop(element) {
    return element.matches(DIALOG_SELECTOR)
  }

  function openDialog(dialog) {
    if (dialog && !dialog.open) {
      dialog.showModal()
    }
  }

  function closeDialog(dialog) {
    if (dialog && dialog.open) {
      dialog.close()
    }
  }

  function confirmWithDialog(question) {
    const confirmDialog = document.getElementById(CONFIRM_DIALOG_ID)
    if (!confirmDialog) {
      return Promise.resolve(window.confirm(question))
    }
    if (confirmDialog.open) {
      return Promise.resolve(false)
    }
    confirmDialog.querySelector('[data-confirm-question]').textContent = question
    confirmDialog.returnValue = ''
    return new Promise(function (resolve) {
      confirmDialog.addEventListener('close', function () {
        resolve(confirmDialog.returnValue === CONFIRMED_RETURN_VALUE)
      }, { once: true })
      confirmDialog.showModal()
    })
  }

  function rememberDialogWhenResponseLandsOutside(event) {
    const swapTarget = event.detail.target
    const requestingElement = event.detail.requestConfig && event.detail.requestConfig.elt
    const requestingDialog = requestingElement && requestingElement.closest(DIALOG_SELECTOR)
    if (requestingDialog && !requestingDialog.contains(swapTarget)) {
      dialogsToCloseAfterSwap.set(event.detail.xhr, requestingDialog)
    }
  }

  function settleDialogsAfterSwap(event) {
    const swapTarget = event.detail.target
    if (swapTarget.matches(DIALOG_SELECTOR) && swapTarget.isConnected) {
      openDialog(swapTarget)
    }
    closeDialog(dialogsToCloseAfterSwap.get(event.detail.xhr))
    dialogsToCloseAfterSwap.delete(event.detail.xhr)
  }

  document.addEventListener('pointerdown', function (event) {
    pointerPressStartedOnBackdrop = isDialogBackdrop(event.target)
  })

  document.addEventListener('click', function (event) {
    const opener = event.target.closest('[data-dialog-open]')
    if (opener) {
      event.preventDefault()
      openDialog(document.getElementById(opener.dataset.dialogOpen))
      return
    }
    const closer = event.target.closest('[data-dialog-close]')
    const closerDialog = closer && closer.closest('dialog')
    if (closerDialog) {
      event.preventDefault()
      closeDialog(closerDialog)
      return
    }
    const pressedAndReleasedOnBackdrop = pointerPressStartedOnBackdrop && isDialogBackdrop(event.target)
    pointerPressStartedOnBackdrop = false
    if (pressedAndReleasedOnBackdrop) {
      closeDialog(event.target)
    }
  })

  function emptyRemoteDialogOnceHidden(dialog) {
    requestAnimationFrame(function () {
      const exitAnimations = dialog.getAnimations().map(function (animation) {
        return animation.finished.catch(function () {})
      })
      Promise.all(exitAnimations).then(function () {
        if (!dialog.open) {
          dialog.replaceChildren()
        }
      })
    })
  }

  document.addEventListener('close', function (event) {
    if (event.target.matches('dialog[data-dialog-remote]')) {
      emptyRemoteDialogOnceHidden(event.target)
    }
  }, true)

  document.addEventListener('htmx:beforeSwap', rememberDialogWhenResponseLandsOutside)
  document.addEventListener('htmx:afterSwap', settleDialogsAfterSwap)

  document.addEventListener('dialog:close', function (event) {
    closeDialog(event.target.closest('dialog'))
  })

  document.addEventListener('htmx:confirm', function (event) {
    if (!event.detail.question) {
      return
    }
    event.preventDefault()
    confirmWithDialog(event.detail.question).then(function (isConfirmed) {
      if (isConfirmed) {
        event.detail.issueRequest(true)
      }
    })
  })

  window.sloppyConfirm = confirmWithDialog
})()
