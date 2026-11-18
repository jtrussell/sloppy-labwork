(function () {
  const STORAGE_KEY = 'keychain-preserved-scroll-position'
  const PAGE_RELOADING_HEADERS = ['HX-Redirect', 'HX-Refresh', 'HX-Location']
  const HTMX_REQUEST_SELECTOR = '[hx-get], [hx-post], [hx-put], [hx-patch], [hx-delete]'

  function rememberScrollPosition() {
    try {
      const remembered = { pathname: window.location.pathname, top: window.scrollY }
      window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(remembered))
    } catch (storageError) {
      return
    }
  }

  function takeRememberedScrollPosition() {
    try {
      const remembered = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY))
      window.sessionStorage.removeItem(STORAGE_KEY)
      return remembered
    } catch (storageError) {
      return null
    }
  }

  function restoreScrollPosition() {
    const remembered = takeRememberedScrollPosition()
    if (remembered && remembered.pathname === window.location.pathname) {
      window.scrollTo({ top: Number(remembered.top), behavior: 'instant' })
    }
  }

  function opensInThisTab(clickEvent) {
    return clickEvent.button === 0 &&
      !clickEvent.metaKey && !clickEvent.ctrlKey && !clickEvent.shiftKey && !clickEvent.altKey
  }

  function rememberWhenInsidePreservingForm(event) {
    const preservingForm = event.target.closest('form[data-preserve-scroll]')
    const isHandledByHtmx = event.target.closest(HTMX_REQUEST_SELECTOR)
    if (preservingForm && !isHandledByHtmx) rememberScrollPosition()
  }

  function reloadsThePage(xhr) {
    return PAGE_RELOADING_HEADERS.some(function (header) {
      return !!xhr.getResponseHeader(header)
    })
  }

  document.addEventListener('click', function (event) {
    const preservingLink = event.target.closest('a[data-preserve-scroll]')
    if (preservingLink && opensInThisTab(event)) rememberScrollPosition()
  })

  document.addEventListener('change', rememberWhenInsidePreservingForm, true)
  document.addEventListener('submit', rememberWhenInsidePreservingForm, true)

  document.addEventListener('htmx:afterRequest', function (event) {
    const requestingElement = event.detail.elt
    if (requestingElement.closest('[data-preserve-scroll]') && reloadsThePage(event.detail.xhr)) {
      rememberScrollPosition()
    }
  })

  restoreScrollPosition()
})()
