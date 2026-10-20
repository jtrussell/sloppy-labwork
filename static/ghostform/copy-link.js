document.querySelectorAll('[data-copy-link]').forEach(function(button) {
  const originalLabel = button.textContent
  const copiedLabel = originalLabel.replace('⚙️', '✅')

  button.addEventListener('click', function() {
    navigator.clipboard.writeText(button.dataset.copyLink).then(function() {
      button.textContent = copiedLabel
      setTimeout(function() {
        button.textContent = originalLabel
      }, 2000)
    })
  })
})
