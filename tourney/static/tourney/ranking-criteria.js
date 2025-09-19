// Ranking Criteria Management
class RankingCriteriaManager {
    constructor(containerSelector, inputSelector = null) {
        this.availableCriteria = [
            { key: 'wins', name: 'Wins', description: 'Number of match wins' },
            { key: 'losses', name: 'Losses', description: 'Number of match losses (fewer is better)' },
            { key: 'points', name: 'Points', description: 'Number of points (2 for win, 1 for tie)' },
            { key: 'strength_of_schedule', name: 'Strength of Schedule', description: 'Average points of opponents faced' },
            { key: 'head_to_head', name: 'Head-to-Head', description: 'Wins against tied opponents' },
            { key: 'seed', name: 'Seed', description: 'Original tournament seed (lower is better)' },
            { key: 'random', name: 'Random', description: 'Random tiebreaker' }
        ];

        this.criteriaContainer = document.querySelector(containerSelector);
        this.criteriaInput = inputSelector ? document.querySelector(inputSelector) : null;
        this.currentCriteria = [];

        this.initializeCriteria();
    }
    
    initializeCriteria() {
        // Check if there's initial criteria data from the template
        if (window.currentCriteriaData && window.currentCriteriaData.length > 0) {
            this.currentCriteria = window.currentCriteriaData;
        } else {
            // Use default criteria if no data is available
            this.currentCriteria = [
                { key: 'points', enabled: true },
                { key: 'wins', enabled: true },
                { key: 'strength_of_schedule', enabled: true },
                { key: 'seed', enabled: true }
            ];
        }

        // Ensure all available criteria are represented
        this.availableCriteria.forEach(available => {
            if (!this.currentCriteria.find(c => c.key === available.key)) {
                this.currentCriteria.push({ key: available.key, enabled: false });
            }
        });

        this.renderCriteria();
    }
    
    renderCriteria() {
        this.criteriaContainer.innerHTML = '';
        
        this.currentCriteria.forEach((criterion, index) => {
            const criteriaData = this.availableCriteria.find(c => c.key === criterion.key);
            if (!criteriaData) return;
            
            const item = document.createElement('div');
            item.className = `drag-drop-item ranking-criteria-item ${criterion.enabled ? '' : 'disabled'}`;
            item.dataset.index = index;
            item.dataset.key = criterion.key;

            item.innerHTML = `
                <div class="drag-handle">⋮⋮</div>
                <div class="drag-drop-content criteria-info">
                    <div class="criteria-name">${criteriaData.name}</div>
                    <div class="criteria-description">${criteriaData.description}</div>
                </div>
                <div class="drag-drop-actions criteria-toggle">
                    <div class="toggle-switch ${criterion.enabled ? 'enabled' : ''}" data-index="${index}">
                        <div class="toggle-slider"></div>
                    </div>
                </div>
            `;
            
            this.criteriaContainer.appendChild(item);
            
            // Add drop indicator
            if (index < this.currentCriteria.length - 1) {
                const dropIndicator = document.createElement('div');
                dropIndicator.className = 'drop-indicator';
                dropIndicator.dataset.position = index + 1;
                this.criteriaContainer.appendChild(dropIndicator);
            }
        });
        
        this.setupDragAndDrop();
        this.setupToggleSwitches();
        this.updateCriteriaInput();
    }
    
    setupToggleSwitches() {
        const toggles = this.criteriaContainer.querySelectorAll('.toggle-switch');
        toggles.forEach(toggle => {
            toggle.addEventListener('click', () => {
                const index = parseInt(toggle.dataset.index);
                this.currentCriteria[index].enabled = !this.currentCriteria[index].enabled;
                this.renderCriteria();
            });
        });
    }
    
    setupDragAndDrop() {
        const items = this.criteriaContainer.querySelectorAll('.ranking-criteria-item');

        items.forEach(item => {
            item.draggable = true; // Enable dragging

            item.addEventListener('dragstart', (e) => {
                item.classList.add('dragging');
                e.dataTransfer.setData('text/plain', item.dataset.index);
            });
            
            item.addEventListener('dragend', () => {
                item.classList.remove('dragging');
                // Hide all drop indicators
                this.criteriaContainer.querySelectorAll('.drop-indicator').forEach(indicator => {
                    indicator.classList.remove('active');
                });
            });
            
            item.addEventListener('dragover', (e) => {
                e.preventDefault();
            });
            
            item.addEventListener('drop', (e) => {
                e.preventDefault();
                const draggedIndex = parseInt(e.dataTransfer.getData('text/plain'));
                const targetIndex = parseInt(item.dataset.index);
                
                if (draggedIndex !== targetIndex) {
                    const draggedItem = this.currentCriteria.splice(draggedIndex, 1)[0];
                    this.currentCriteria.splice(targetIndex, 0, draggedItem);
                    this.renderCriteria();
                }
            });
        });
        
        // Handle drop indicators
        const dropIndicators = this.criteriaContainer.querySelectorAll('.drop-indicator');
        dropIndicators.forEach(indicator => {
            indicator.addEventListener('dragover', (e) => {
                e.preventDefault();
                indicator.classList.add('active');
            });
            
            indicator.addEventListener('dragleave', () => {
                indicator.classList.remove('active');
            });
            
            indicator.addEventListener('drop', (e) => {
                e.preventDefault();
                const draggedIndex = parseInt(e.dataTransfer.getData('text/plain'));
                const targetPosition = parseInt(indicator.dataset.position);
                
                const draggedItem = this.currentCriteria.splice(draggedIndex, 1)[0];
                this.currentCriteria.splice(targetPosition, 0, draggedItem);
                this.renderCriteria();
            });
        });
    }
    
    updateCriteriaInput() {
        // Update individual form fields based on the visual order in the DOM
        const criteriaItems = this.criteriaContainer.querySelectorAll('.ranking-criteria-item');
        let enabledOrder = 1;

        criteriaItems.forEach((item) => {
            const criterionKey = item.dataset.key;
            const criterion = this.currentCriteria.find(c => c.key === criterionKey);

            if (!criterion) return;

            const enabledField = document.querySelector(`input[name="criterion_${criterionKey}_enabled"]`);
            const orderField = document.querySelector(`input[name="criterion_${criterionKey}_order"]`);

            if (enabledField) {
                enabledField.value = criterion.enabled ? 'on' : '';
            }

            if (orderField) {
                if (criterion.enabled) {
                    orderField.value = enabledOrder;
                    enabledOrder++;
                } else {
                    orderField.value = '';
                }
            }
        });
    }
}

// Tournament form utility functions
function setupPlayoffToggle(checkboxSelector, optionsSelector) {
    const playoffCheckbox = document.querySelector(checkboxSelector);
    const playoffOptions = document.querySelector(optionsSelector);
    
    function togglePlayoffOptions() {
        if (playoffCheckbox.checked) {
            playoffOptions.style.display = 'block';
        } else {
            playoffOptions.style.display = 'none';
        }
    }
    
    // Initial state
    togglePlayoffOptions();
    
    // Toggle on change
    playoffCheckbox.addEventListener('change', togglePlayoffOptions);
}