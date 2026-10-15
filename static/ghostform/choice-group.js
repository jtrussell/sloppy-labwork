function filterChoiceOptions(filterInput) {
  const query = filterInput.value.trim().toLowerCase()
  filterInput
    .closest('[data-choice-group]')
    .querySelectorAll('[data-choice-label]')
    .forEach((option) => {
      option.hidden = !option.dataset.choiceLabel.toLowerCase().includes(query)
    })
}

function describeSelectedCount(selectedCount, maximumSelections) {
  return maximumSelections
    ? `${selectedCount} of ${maximumSelections} selected`
    : `${selectedCount} selected`
}

function updateChoiceGroup(choiceGroup) {
  const checkboxes = [
    ...choiceGroup.querySelectorAll('input[type="checkbox"]'),
  ]
  const selectedCount = checkboxes.filter((checkbox) => checkbox.checked).length
  const maximumSelections = Number(choiceGroup.dataset.maximumSelections) || 0
  choiceGroup.querySelector('[data-choice-count]').textContent =
    describeSelectedCount(selectedCount, maximumSelections)
  if (!maximumSelections) return
  const isAtMaximum = selectedCount >= maximumSelections
  checkboxes.forEach((checkbox) => {
    checkbox.disabled = isAtMaximum && !checkbox.checked
  })
}

function updateChoiceGroupsWithin(root) {
  root.querySelectorAll('[data-choice-group]').forEach(updateChoiceGroup)
}

document.addEventListener('input', (event) => {
  if (event.target.matches('[data-choice-filter]')) {
    filterChoiceOptions(event.target)
  }
})

document.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && event.target.matches('[data-choice-filter]')) {
    event.preventDefault()
  }
})

document.addEventListener('change', (event) => {
  const choiceGroup = event.target.closest('[data-choice-group]')
  if (choiceGroup && event.target.type === 'checkbox') {
    updateChoiceGroup(choiceGroup)
  }
})

document.addEventListener('DOMContentLoaded', () =>
  updateChoiceGroupsWithin(document),
)
document.addEventListener('htmx:load', (event) =>
  updateChoiceGroupsWithin(event.detail.elt),
)
