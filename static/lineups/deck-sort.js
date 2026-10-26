document.addEventListener('alpine:init', () => {
  Alpine.data('deckList', (updateUrl, csrfToken) => ({
    handleSort() {
      const ids = Array.from(
        this.$el.querySelectorAll('.sortable__item')
      ).map((item) => item.dataset.key)

      const formData = new FormData()
      for (const id of ids) formData.append('order[]', id)

      fetch(updateUrl, {
        method: 'POST',
        headers: { 'X-CSRFToken': csrfToken },
        body: formData,
      })
    },
  }))
})
