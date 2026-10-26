function setupPlayoffToggle(checkboxSelector, targetSelector) {
    const checkbox = document.querySelector(checkboxSelector);
    const target = document.querySelector(targetSelector);

    if (!checkbox || !target) return;

    function updateVisibility() {
        target.hidden = !checkbox.checked;
    }

    updateVisibility();

    checkbox.addEventListener('change', updateVisibility);
}
