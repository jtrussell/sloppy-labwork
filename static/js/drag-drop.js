// Consolidated Drag and Drop Manager
class DragDropManager {
  constructor(containerSelector, options = {}) {
    this.container = document.querySelector(containerSelector)
    this.options = {
      itemSelector: '.drag-drop-item',
      handleSelector: '.drag-handle',
      dropIndicatorClass: 'drop-indicator',
      draggingClass: 'dragging',
      activeIndicatorClass: 'active',
      onReorder: null,
      onDragStart: null,
      onDragEnd: null,
      ...options,
    }

    this.init()
  }

  init() {
    if (!this.container) return
    this.setupDragAndDrop()
  }

  setupDragAndDrop() {
    const items = this.container.querySelectorAll(this.options.itemSelector)

    items.forEach((item) => {
      item.draggable = true

      item.addEventListener('dragstart', (e) => {
        item.classList.add(this.options.draggingClass)
        e.dataTransfer.setData('text/plain', this.getItemId(item))

        if (this.options.onDragStart) {
          this.options.onDragStart(item, e)
        }
      })

      item.addEventListener('dragend', (e) => {
        item.classList.remove(this.options.draggingClass)
        this.hideAllDropIndicators()

        if (this.options.onDragEnd) {
          this.options.onDragEnd(item, e)
        }
      })

      item.addEventListener('dragover', (e) => {
        e.preventDefault()
      })

      item.addEventListener('drop', (e) => {
        e.preventDefault()
        const draggedId = e.dataTransfer.getData('text/plain')
        const targetId = this.getItemId(item)

        if (draggedId !== targetId) {
          this.reorderItems(draggedId, targetId)
        }
      })
    })

    // Handle drop indicators if they exist
    this.setupDropIndicators()
  }

  setupDropIndicators() {
    const indicators = this.container.querySelectorAll(
      `.${this.options.dropIndicatorClass}`
    )

    indicators.forEach((indicator) => {
      indicator.addEventListener('dragover', (e) => {
        e.preventDefault()
        indicator.classList.add(this.options.activeIndicatorClass)
      })

      indicator.addEventListener('dragleave', () => {
        indicator.classList.remove(this.options.activeIndicatorClass)
      })

      indicator.addEventListener('drop', (e) => {
        e.preventDefault()
        const draggedId = e.dataTransfer.getData('text/plain')
        const targetPosition = parseInt(indicator.dataset.position)

        this.reorderToPosition(draggedId, targetPosition)
      })
    })
  }

  getItemId(item) {
    return (
      item.dataset.playerId || item.dataset.index || item.dataset.key || item.id
    )
  }

  reorderItems(draggedId, targetId) {
    const items = Array.from(
      this.container.querySelectorAll(this.options.itemSelector)
    )
    const draggedItem = items.find((item) => this.getItemId(item) === draggedId)
    const targetItem = items.find((item) => this.getItemId(item) === targetId)

    if (draggedItem && targetItem) {
      const draggedIndex = items.indexOf(draggedItem)
      const targetIndex = items.indexOf(targetItem)

      if (draggedIndex < targetIndex) {
        targetItem.parentNode.insertBefore(draggedItem, targetItem.nextSibling)
      } else {
        targetItem.parentNode.insertBefore(draggedItem, targetItem)
      }

      if (this.options.onReorder) {
        this.options.onReorder(this.getOrderedItems())
      }
    }
  }

  reorderToPosition(draggedId, targetPosition) {
    const items = Array.from(
      this.container.querySelectorAll(this.options.itemSelector)
    )
    const draggedItem = items.find((item) => this.getItemId(item) === draggedId)

    if (draggedItem) {
      const draggedIndex = items.indexOf(draggedItem)

      if (targetPosition <= draggedIndex) {
        // Insert before the item at target position
        const targetItem = items[targetPosition]
        if (targetItem) {
          targetItem.parentNode.insertBefore(draggedItem, targetItem)
        }
      } else {
        // Insert after the item at target position - 1
        const targetItem = items[targetPosition - 1]
        if (targetItem) {
          targetItem.parentNode.insertBefore(
            draggedItem,
            targetItem.nextSibling
          )
        }
      }

      if (this.options.onReorder) {
        this.options.onReorder(this.getOrderedItems())
      }
    }
  }

  getOrderedItems() {
    return Array.from(
      this.container.querySelectorAll(this.options.itemSelector)
    ).map((item) => this.getItemId(item))
  }

  hideAllDropIndicators() {
    this.container
      .querySelectorAll(`.${this.options.dropIndicatorClass}`)
      .forEach((indicator) => {
        indicator.classList.remove(this.options.activeIndicatorClass)
      })
  }

  refresh() {
    // Re-setup drag and drop after content changes
    this.setupDragAndDrop()
  }
}

// Seeding-specific drag and drop manager
class SeedingDragDropManager extends DragDropManager {
  constructor(containerSelector, updateUrl, csrfToken) {
    super(containerSelector, {
      itemSelector: '.seeding-item',
      onReorder: (orderedIds) => this.updateSeedingOrder(orderedIds),
    })

    this.updateUrl = updateUrl
    this.csrfToken = csrfToken
  }

  updateSeedingOrder(playerIds) {
    if (typeof htmx !== 'undefined') {
      htmx.ajax('POST', this.updateUrl, {
        values: {
          player_order: playerIds.join(','),
        },
        target: '#seeding-list',
        swap: 'innerHTML',
      })
    }
  }
}

// Ranking criteria-specific drag and drop manager
class RankingCriteriaDragDropManager extends DragDropManager {
  constructor(containerSelector, availableCriteria, currentCriteria) {
    super(containerSelector, {
      itemSelector: '.ranking-criteria-item',
      onReorder: () => this.updateCriteriaInput(),
    })

    this.availableCriteria = availableCriteria
    this.currentCriteria = currentCriteria
  }

  updateCriteriaInput() {
    // Update individual form fields based on the visual order in the DOM
    const criteriaItems = this.container.querySelectorAll(
      '.ranking-criteria-item'
    )
    let enabledOrder = 1

    criteriaItems.forEach((item) => {
      const criterionKey = item.dataset.key
      const criterion = this.currentCriteria.find((c) => c.key === criterionKey)

      if (!criterion) return

      const enabledField = document.querySelector(
        `input[name="criterion_${criterionKey}_enabled"]`
      )
      const orderField = document.querySelector(
        `input[name="criterion_${criterionKey}_order"]`
      )

      if (enabledField) {
        enabledField.value = criterion.enabled ? 'on' : ''
      }

      if (orderField) {
        if (criterion.enabled) {
          orderField.value = enabledOrder
          enabledOrder++
        } else {
          orderField.value = ''
        }
      }
    })
  }
}

// Utility functions for backward compatibility
function initializeSeedingDragDrop(containerSelector, updateUrl, csrfToken) {
  return new SeedingDragDropManager(containerSelector, updateUrl, csrfToken)
}

function initializeRankingCriteriaDragDrop(
  containerSelector,
  availableCriteria,
  currentCriteria
) {
  return new RankingCriteriaDragDropManager(
    containerSelector,
    availableCriteria,
    currentCriteria
  )
}
