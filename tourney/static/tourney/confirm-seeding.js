document.addEventListener('alpine:init', () => {
  Alpine.data('seedingList', (updateUrl) => ({
    handleSort() {
      const playerIds = Array.from(
        this.$el.querySelectorAll('.seeding-item')
      ).map((item) => item.dataset.playerId)

      htmx.ajax('POST', updateUrl, {
        values: { player_order: playerIds.join(',') },
        target: '#seeding-list',
        swap: 'innerHTML',
      })
    },
  }))
})
