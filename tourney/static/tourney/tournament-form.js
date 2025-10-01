function setupPlayoffToggle(checkboxSelector, targetSelector) {
    const checkbox = document.querySelector(checkboxSelector);
    const target = document.querySelector(targetSelector);

    if (!checkbox || !target) return;

    function updateVisibility() {
        target.style.display = checkbox.checked ? 'block' : 'none';
    }

    updateVisibility();

    checkbox.addEventListener('change', updateVisibility);
}
