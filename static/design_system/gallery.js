(function () {
  const themeButtons = document.querySelectorAll('[data-ds-theme]')
  const root = document.documentElement

  function markPressed(theme) {
    themeButtons.forEach(function (button) {
      button.setAttribute('aria-pressed', String(button.dataset.dsTheme === theme))
    })
  }

  themeButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      root.dataset.theme = button.dataset.dsTheme
      markPressed(button.dataset.dsTheme)
    })
  })

  markPressed(root.dataset.theme || '0')

  document.addEventListener('click', function (event) {
    const confirmDemoButton = event.target.closest('[data-ds-confirm-demo]')
    if (!confirmDemoButton || !window.sloppyConfirm) {
      return
    }
    const result = confirmDemoButton.parentElement.querySelector('[data-ds-confirm-result]')
    window.sloppyConfirm(confirmDemoButton.dataset.dsConfirmDemo).then(function (isConfirmed) {
      result.textContent = isConfirmed ? 'Confirmed.' : 'Cancelled.'
    })
  })
})()
