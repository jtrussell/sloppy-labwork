document.addEventListener('alpine:init', () => {
  Alpine.data('rankingCriteria', (initialData) => ({
    order: [],
    enabled: {},

    init() {
      this.order = initialData.map((c) => c.key)
      this.enabled = Object.fromEntries(
        initialData.map((c) => [c.key, Boolean(c.enabled)])
      )
    },

    handleSort(key, position) {
      const currentIndex = this.order.indexOf(key)
      if (currentIndex === -1 || currentIndex === position) return
      this.order.splice(currentIndex, 1)
      this.order.splice(position, 0, key)
    },

    toggle(key) {
      this.enabled[key] = !this.enabled[key]
    },

    orderFor(key) {
      if (!this.enabled[key]) return ''
      let n = 1
      for (const k of this.order) {
        if (k === key) return n
        if (this.enabled[k]) n++
      }
      return ''
    },
  }))
})
