document.addEventListener('alpine:init', () => {
  Alpine.data('podList', (initialPods, maximumPods) => ({
    pods: [],
    nextKey: 0,
    maximumPods,

    init() {
      this.pods = initialPods.map((pod) => this.buildPod(pod.id, pod.name))
    },

    buildPod(id, name) {
      this.nextKey += 1
      return { key: this.nextKey, id: id || '', name }
    },

    canAddPod() {
      return this.pods.length < this.maximumPods
    },

    addPod() {
      if (!this.canAddPod()) return
      this.pods.push(this.buildPod('', this.suggestPodName()))
      this.$nextTick(() => {
        const inputs = this.$root.querySelectorAll('.pod-name-input')
        inputs[inputs.length - 1]?.focus()
      })
    },

    removePod(key) {
      this.pods = this.pods.filter((pod) => pod.key !== key)
    },

    suggestPodName() {
      const usedNames = new Set(this.pods.map((pod) => pod.name.toLowerCase()))
      for (let i = 0; i < 26; i++) {
        const name = `Pod ${String.fromCharCode(65 + i)}`
        if (!usedNames.has(name.toLowerCase())) return name
      }
      return `Pod ${this.pods.length + 1}`
    },
  }))
})
