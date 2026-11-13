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

document.addEventListener('alpine:init', () => {
    Alpine.data('lineupSettings', (initialSettings) => ({
        templateId: initialSettings.templateId,
        isRequired: initialSettings.isRequired,
        templateDeckCounts: initialSettings.templateDeckCounts,

        get needsDeckCount() {
            return this.isRequired && !this.templateId;
        },

        get usesTemplateDeckCount() {
            return this.isRequired && Boolean(this.templateId);
        },

        get submitsDecksInSession() {
            return !this.isRequired && Boolean(this.templateId);
        },

        get templateDeckCount() {
            return this.templateDeckCounts[this.templateId];
        },
    }));
});
