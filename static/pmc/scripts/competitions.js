(function () {
	function openDialogFor(opener) {
		var dialog = document.getElementById(opener.dataset.dialogOpen)
		if (dialog && !dialog.open) {
			dialog.showModal()
		}
	}

	function closeActionMenusOutside(target, keepOpenMenu) {
		document.querySelectorAll('details.action-menu[open]').forEach(function (menu) {
			if (menu !== keepOpenMenu || !menu.contains(target)) {
				menu.removeAttribute('open')
			}
		})
	}

	document.addEventListener('click', function (event) {
		var opener = event.target.closest('[data-dialog-open]')
		if (opener) {
			closeActionMenusOutside(event.target, null)
			openDialogFor(opener)
			return
		}
		closeActionMenusOutside(event.target, event.target.closest('details.action-menu'))
	})

	document.addEventListener('keydown', function (event) {
		if (event.key === 'Escape') {
			closeActionMenusOutside(null, null)
		}
	})
}())
