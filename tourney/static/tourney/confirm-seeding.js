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

  Alpine.data('podAssignment', (updateUrl) => ({
    handleSort() {
      const podAssignments = {}
      this.$root.querySelectorAll('[data-pod-id]').forEach((podList) => {
        podAssignments[podList.dataset.podId] = Array.from(
          podList.querySelectorAll('[data-stage-player-id]')
        ).map((item) => item.dataset.stagePlayerId)
      })

      htmx.ajax('POST', updateUrl, {
        values: { pod_assignments: JSON.stringify(podAssignments) },
        target: '#seeding-list',
        swap: 'innerHTML',
      })
    },
  }))
})
