(function () {
  const MENU_SELECTOR = 'details[data-menu]'
  const OPEN_MENU_SELECTOR = 'details[data-menu][open]'
  const ANCHORED_MENU_SELECTOR = 'details.action-menu[data-menu]'
  const MENU_GAP_PX = 4

  function closeMenusExcept(keptMenu) {
    document.querySelectorAll(OPEN_MENU_SELECTOR).forEach(function (menu) {
      if (menu !== keptMenu) menu.open = false
    })
  }

  function closeMenuReturningFocus(menu) {
    menu.querySelector('summary').focus()
    menu.open = false
  }

  function anchorListToTrigger(menu) {
    const triggerBox = menu.querySelector('summary').getBoundingClientRect()
    const list = menu.querySelector('.action-menu__list')
    const opensUpward = triggerBox.bottom + list.offsetHeight + MENU_GAP_PX > window.innerHeight &&
      triggerBox.top - list.offsetHeight - MENU_GAP_PX > 0
    menu.style.setProperty('--menu-right', (document.documentElement.clientWidth - triggerBox.right) + 'px')
    menu.style.setProperty('--menu-top', opensUpward ? 'auto' : (triggerBox.bottom + MENU_GAP_PX) + 'px')
    menu.style.setProperty('--menu-bottom', opensUpward ? (window.innerHeight - triggerBox.top + MENU_GAP_PX) + 'px' : 'auto')
    menu.toggleAttribute('data-anchored', true)
  }

  function closeAnchoredMenus() {
    document.querySelectorAll(ANCHORED_MENU_SELECTOR + '[open]').forEach(function (menu) {
      menu.open = false
    })
  }

  document.addEventListener('pointerdown', function (event) {
    closeMenusExcept(event.target.closest(MENU_SELECTOR))
  })

  document.addEventListener('toggle', function (event) {
    if (!event.target.matches(MENU_SELECTOR) || !event.target.open) return
    closeMenusExcept(event.target)
    if (event.target.matches(ANCHORED_MENU_SELECTOR)) anchorListToTrigger(event.target)
  }, true)

  document.addEventListener('click', function (event) {
    const menu = event.target.closest(OPEN_MENU_SELECTOR)
    const chosenItem = event.target.closest('a, button')
    if (menu && chosenItem) {
      closeMenuReturningFocus(menu)
    }
  }, true)

  document.addEventListener('focusout', function (event) {
    const menu = event.target.closest && event.target.closest(OPEN_MENU_SELECTOR)
    if (menu && event.relatedTarget && !menu.contains(event.relatedTarget)) {
      menu.open = false
    }
  })

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return
    const openMenu = document.querySelector(OPEN_MENU_SELECTOR)
    if (!openMenu) return
    event.preventDefault()
    event.stopPropagation()
    closeMenuReturningFocus(openMenu)
  }, true)

  document.addEventListener('scroll', function (event) {
    const scrolledInsideMenu = event.target.closest && event.target.closest(OPEN_MENU_SELECTOR)
    if (!scrolledInsideMenu) closeAnchoredMenus()
  }, true)
  window.addEventListener('resize', closeAnchoredMenus)
})()
