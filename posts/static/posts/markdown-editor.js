(function () {
  function showMode(editor, chosenButton) {
    const isPreview = chosenButton.dataset.markdownMode === 'preview'
    editor.querySelectorAll('[data-markdown-mode]').forEach(function (button) {
      button.setAttribute('aria-pressed', String(button === chosenButton))
    })
    editor.querySelector('textarea').hidden = isPreview
    editor.querySelector('[data-markdown-preview]').hidden = !isPreview
    return isPreview
  }

  function renderPreview(editor, sourceButton) {
    htmx.ajax('POST', editor.dataset.previewUrl, {
      source: sourceButton,
      target: editor.querySelector('[data-markdown-preview]'),
      swap: 'innerHTML',
      values: { markdown: editor.querySelector('textarea').value },
    })
  }

  document.addEventListener('click', function (event) {
    const modeButton = event.target.closest('[data-markdown-mode]')
    if (!modeButton) return
    const editor = modeButton.closest('[data-markdown-editor]')
    if (showMode(editor, modeButton)) renderPreview(editor, modeButton)
  })
})()
