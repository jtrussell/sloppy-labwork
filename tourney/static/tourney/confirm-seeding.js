let seedingManager;

function initializeSeedingDragDrop() {
    const container = document.querySelector('#sortable-seeding');
    if (!container) return;

    const updateUrl = container.dataset.updateUrl;
    seedingManager = new SeedingDragDropManager('#sortable-seeding', updateUrl);
}

document.addEventListener('DOMContentLoaded', function() {
    initializeSeedingDragDrop();
});

document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'seeding-list') {
        initializeSeedingDragDrop();
    }
});
