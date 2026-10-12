document.addEventListener('alpine:init', () => {
  Alpine.data('formPicker', () => ({
    selectedValue: '',
    selectedTitle: '',
    selectedMeta: '',
    selectedPreviewCode: '',
    previewUrlTemplate: '',
    loadedPreviewCode: '',
    isOpen: false,
    isPreviewOpen: false,

    init() {
      const pickerData = this.$el.dataset
      this.selectedValue = pickerData.selectedValue
      this.selectedTitle = pickerData.selectedTitle
      this.selectedMeta = pickerData.selectedMeta
      this.selectedPreviewCode = pickerData.selectedPreviewCode
      this.previewUrlTemplate = pickerData.previewUrlTemplate
    },

    toggleOpen() {
      this.isOpen = !this.isOpen
      if (this.isOpen) this.$nextTick(() => this.$refs.search.focus())
    },

    isSelected(value) {
      return this.selectedValue === value
    },

    select(optionElement) {
      const optionData = optionElement.dataset
      this.selectedValue = optionData.value
      this.selectedTitle = optionData.title
      this.selectedMeta = optionData.meta
      this.selectedPreviewCode = optionData.previewCode
      this.isOpen = false
      this.isPreviewOpen = false
      this.loadedPreviewCode = ''
      this.$refs.preview.innerHTML = ''
    },

    async togglePreview() {
      this.isPreviewOpen = !this.isPreviewOpen
      if (!this.isPreviewOpen || this.loadedPreviewCode === this.selectedPreviewCode) return

      const previewCode = this.selectedPreviewCode
      const previewUrl = this.previewUrlTemplate.replace(
        'FORM_CODE',
        encodeURIComponent(previewCode),
      )
      const response = await fetch(previewUrl, { credentials: 'same-origin' })
      if (previewCode !== this.selectedPreviewCode) return
      const isPreviewMarkup = response.ok && !response.redirected
      this.$refs.preview.innerHTML = isPreviewMarkup
        ? await response.text()
        : '<p class="form-picker__empty">Could not load the questions.</p>'
      this.loadedPreviewCode = isPreviewMarkup ? previewCode : ''
    },
  }))
})
