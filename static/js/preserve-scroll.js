(function () {
  const STORAGE_KEY = 'preserved-scroll-position'

  function rememberScrollPosition() {
    try {
      window.sessionStorage.setItem(STORAGE_KEY, String(window.scrollY))
    } catch (storageError) {
      return
    }
  }

  function takeRememberedScrollPosition() {
    try {
      const rememberedPosition = window.sessionStorage.getItem(STORAGE_KEY)
      window.sessionStorage.removeItem(STORAGE_KEY)
      return rememberedPosition
    } catch (storageError) {
      return null
    }
  }

  function restoreScrollPosition() {
    const rememberedPosition = takeRememberedScrollPosition()
    if (rememberedPosition !== null) {
      window.scrollTo({ top: Number(rememberedPosition), behavior: 'instant' })
    }
  }

  function opensInThisTab(clickEvent) {
    return clickEvent.button === 0 &&
      !clickEvent.metaKey && !clickEvent.ctrlKey && !clickEvent.shiftKey && !clickEvent.altKey
  }

  function rememberWhenInsidePreservingForm(event) {
    if (event.target.closest('form[data-preserve-scroll]')) rememberScrollPosition()
  }

  document.addEventListener('click', function (event) {
    const preservingLink = event.target.closest('a[data-preserve-scroll]')
    if (preservingLink && opensInThisTab(event)) rememberScrollPosition()
  })

  document.addEventListener('change', rememberWhenInsidePreservingForm, true)
  document.addEventListener('submit', rememberWhenInsidePreservingForm, true)

  restoreScrollPosition()
})()
