(function () {
  function openMenus() {
    return document.querySelectorAll('details.action-menu[open]')
  }

  function closeMenusExcept(keptMenu) {
    openMenus().forEach(function (menu) {
      if (menu !== keptMenu) menu.open = false
    })
  }

  document.addEventListener('pointerdown', function (event) {
    closeMenusExcept(event.target.closest('details.action-menu'))
  })

  document.addEventListener('toggle', function (event) {
    if (event.target.matches('details.action-menu') && event.target.open) {
      closeMenusExcept(event.target)
    }
  }, true)

  function closeMenuReturningFocus(menu) {
    menu.querySelector('summary').focus()
    menu.open = false
  }

  document.addEventListener('click', function (event) {
    const item = event.target.closest('.action-menu__item')
    if (!item) return
    const menu = item.closest('details.action-menu')
    if (menu) closeMenuReturningFocus(menu)
  })

  document.addEventListener('focusout', function (event) {
    const menu = event.target.closest && event.target.closest('details.action-menu[open]')
    if (menu && event.relatedTarget && !menu.contains(event.relatedTarget)) {
      menu.open = false
    }
  })

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return
    const menu = event.target.closest && event.target.closest('details.action-menu[open]')
    if (!menu) return
    event.preventDefault()
    event.stopPropagation()
    closeMenuReturningFocus(menu)
  }, true)

  document.addEventListener('cancel', function (event) {
    const menuInsideDialog = event.target.querySelector('details.action-menu[open]')
    if (!menuInsideDialog) return
    event.preventDefault()
    menuInsideDialog.open = false
  }, true)
})()
