(function () {
  const COPIED_LABEL_DURATION_MS = 2000

  function flashCopied(button) {
    const label = button.querySelector('[data-copy-label]') || button
    const originalText = label.dataset.originalText || label.textContent
    label.dataset.originalText = originalText
    label.textContent = 'Copied!'
    setTimeout(function () {
      label.textContent = originalText
    }, COPIED_LABEL_DURATION_MS)
  }

  function findCopySource(button) {
    return button.dataset.copyFrom && document.querySelector(button.dataset.copyFrom)
  }

  function revealCopySource(button) {
    const source = findCopySource(button)
    if (source) {
      source.hidden = false
      source.select()
    }
  }

  function handleCopy(button) {
    const source = findCopySource(button)
    const text = source ? source.value : button.dataset.copyText
    if (!navigator.clipboard) {
      revealCopySource(button)
      return
    }
    navigator.clipboard.writeText(text)
      .then(function () { flashCopied(button) })
      .catch(function () { revealCopySource(button) })
  }

  function handleShare(button) {
    navigator.share({ title: button.dataset.shareTitle, url: button.dataset.shareUrl }).catch(function () {})
  }

  function revealShareButtons(scope) {
    if (navigator.share) {
      scope.querySelectorAll('[data-share-url]').forEach(function (button) { button.hidden = false })
    }
  }

  document.addEventListener('click', function (event) {
    const copyButton = event.target.closest('[data-copy-text], [data-copy-from]')
    if (copyButton) {
      handleCopy(copyButton)
      return
    }
    const shareButton = event.target.closest('[data-share-url]')
    if (shareButton && navigator.share) {
      handleShare(shareButton)
    }
  })

  document.addEventListener('DOMContentLoaded', function () { revealShareButtons(document) })
  document.addEventListener('htmx:load', function (event) { revealShareButtons(event.detail.elt) })
})()
