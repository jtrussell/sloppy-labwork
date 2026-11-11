document.addEventListener('change', (event) => {
  const filterControl = event.target.closest('[data-pod-switcher] select, [data-pod-switcher] input')
  if (filterControl) filterControl.form.submit()
})
