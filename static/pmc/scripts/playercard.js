(function () {
  const SHIELD_SELECTOR = '[data-playercard-reveal]'
  const REVEALED_SELECTOR = '[data-playercard-revealed]'

  document.addEventListener('click', function (event) {
    const shield = event.target.closest(SHIELD_SELECTOR)
    if (!shield) return

    const revealedImage = shield.parentElement.querySelector(REVEALED_SELECTOR)
    shield.remove()
    if (revealedImage) revealedImage.focus()
  })
})()
