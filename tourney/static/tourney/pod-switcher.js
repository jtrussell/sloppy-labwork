document.addEventListener('change', (event) => {
  const podSelect = event.target.closest('[data-pod-switcher] select')
  if (podSelect) podSelect.form.submit()
})
