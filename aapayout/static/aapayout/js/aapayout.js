/**
 * AA-Payout JavaScript
 * Client-side functionality for the Fleet Payout plugin
 */

(function () {
    'use strict';

    // ========================================
    // Initialization
    // ========================================

    document.addEventListener('DOMContentLoaded', function () {
        initializeCharacterAutocomplete();
        initializeISKFormatting();
        initializeFormValidation();
        initializeTooltips();
        initializeConfirmDialogs();
        initializeLootTextCounter();
        initializeInlinePaymentActions();
        initializeParticipantStatusToggles();
        initializeModalAutocomplete();
        initializeCopyOnClick();
        initializeScoutBonusSlider();
    });

    // ========================================
    // Modal Autocomplete Initialization
    // ========================================

    function initializeModalAutocomplete() {
        // Re-initialize autocomplete when participant modal is shown
        const participantModal = document.getElementById('addParticipantModal');
        if (participantModal) {
            participantModal.addEventListener('shown.bs.modal', function () {
                initializeCharacterAutocomplete();
            });

            // Clear the form when modal is hidden
            participantModal.addEventListener('hidden.bs.modal', function () {
                const form = document.getElementById('participant-add-form');
                if (form) {
                    form.reset();
                }
                const suggestionsDiv = document.getElementById('participant-suggestions');
                if (suggestionsDiv) {
                    suggestionsDiv.style.display = 'none';
                    suggestionsDiv.innerHTML = '';
                }
            });
        }
    }

    // ========================================
    // Character Autocomplete
    // ========================================

    function initializeCharacterAutocomplete() {
        const charInputs = document.querySelectorAll('input[name="character_name"]');

        charInputs.forEach(function (input) {
            // Try to find suggestions div - could be #character-suggestions or #participant-suggestions
            let suggestionsDiv = input.parentElement.querySelector('#participant-suggestions');
            if (!suggestionsDiv) {
                suggestionsDiv = document.getElementById('character-suggestions');
            }
            if (!suggestionsDiv) return;

            let debounceTimer;
            let selectedCharacterId = null;

            input.addEventListener('input', function () {
                clearTimeout(debounceTimer);
                const query = this.value.trim();

                if (query.length < 2) {
                    suggestionsDiv.style.display = 'none';
                    suggestionsDiv.innerHTML = '';
                    return;
                }

                debounceTimer = setTimeout(function () {
                    fetchCharacterSuggestions(query, input, suggestionsDiv);
                }, 300);
            });

            // Hide suggestions when clicking outside
            document.addEventListener('click', function (e) {
                if (e.target !== input && !suggestionsDiv.contains(e.target)) {
                    suggestionsDiv.style.display = 'none';
                }
            });

            // Handle keyboard navigation
            input.addEventListener('keydown', function (e) {
                handleAutocompleteKeyboard(e, suggestionsDiv);
            });
        });
    }

    function fetchCharacterSuggestions(query, input, suggestionsDiv) {
        // Get CSRF token
        const csrftoken = getCookie('csrftoken');

        fetch('/payout/api/character-search/?q=' + encodeURIComponent(query), {
            method: 'GET',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json',
            },
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(function (data) {
                displayCharacterSuggestions(data.results || [], input, suggestionsDiv);
            })
            .catch(function (error) {
                console.error('Error fetching character suggestions:', error);
                suggestionsDiv.style.display = 'none';
            });
    }

    function displayCharacterSuggestions(results, input, suggestionsDiv) {
        suggestionsDiv.innerHTML = '';

        if (results.length === 0) {
            suggestionsDiv.style.display = 'none';
            return;
        }

        results.forEach(function (character) {
            const item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action';
            item.textContent = character.character_name;
            item.dataset.characterId = character.character_id;

            item.addEventListener('click', function (e) {
                e.preventDefault();
                input.value = character.character_name;
                input.dataset.characterId = character.character_id;
                suggestionsDiv.style.display = 'none';
            });

            suggestionsDiv.appendChild(item);
        });

        suggestionsDiv.style.display = 'block';
    }

    function handleAutocompleteKeyboard(e, suggestionsDiv) {
        if (suggestionsDiv.style.display === 'none') return;

        const items = suggestionsDiv.querySelectorAll('.list-group-item');
        if (items.length === 0) return;

        let currentIndex = Array.from(items).findIndex(function (item) {
            return item.classList.contains('active');
        });

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (currentIndex < items.length - 1) {
                if (currentIndex >= 0) items[currentIndex].classList.remove('active');
                items[currentIndex + 1].classList.add('active');
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (currentIndex > 0) {
                items[currentIndex].classList.remove('active');
                items[currentIndex - 1].classList.add('active');
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (currentIndex >= 0) {
                items[currentIndex].click();
            }
        } else if (e.key === 'Escape') {
            suggestionsDiv.style.display = 'none';
        }
    }

    // ========================================
    // ISK Formatting
    // ========================================

    function initializeISKFormatting() {
        // Format ISK amounts with thousand separators
        const iskElements = document.querySelectorAll('.isk-amount, [data-isk-format]');

        iskElements.forEach(function (element) {
            const value = parseFloat(element.textContent.replace(/,/g, ''));
            if (!isNaN(value)) {
                element.textContent = formatISK(value);
            }
        });

        // Real-time formatting for input fields
        const iskInputs = document.querySelectorAll('input[name*="price"], input[name*="amount"]');

        iskInputs.forEach(function (input) {
            input.addEventListener('blur', function () {
                const value = parseFloat(this.value.replace(/,/g, ''));
                if (!isNaN(value)) {
                    // Don't format if it's being used in a calculation
                    if (!this.classList.contains('no-format')) {
                        this.value = formatISK(value);
                    }
                }
            });

            input.addEventListener('focus', function () {
                // Remove formatting when focusing for easier editing
                this.value = this.value.replace(/,/g, '');
            });
        });
    }

    function formatISK(value) {
        return value.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    // ========================================
    // Form Validation
    // ========================================

    function initializeFormValidation() {
        // Add Bootstrap validation classes
        const forms = document.querySelectorAll('form[method="post"]');

        forms.forEach(function (form) {
            form.addEventListener('submit', function (e) {
                if (!form.checkValidity()) {
                    e.preventDefault();
                    e.stopPropagation();
                }

                form.classList.add('was-validated');
            });
        });

        // Custom validation for loot text
        const lootTextArea = document.querySelector('textarea[name="raw_loot_text"]');
        if (lootTextArea) {
            lootTextArea.addEventListener('blur', function () {
                validateLootText(this);
            });
        }
    }

    function validateLootText(textarea) {
        const value = textarea.value.trim();
        if (value.length === 0) {
            textarea.setCustomValidity('Loot text cannot be empty');
            return false;
        }

        // Check if it looks like valid EVE loot format (item name + tab/spaces + quantity)
        const lines = value.split('\n').filter(function (line) {
            return line.trim().length > 0;
        });

        if (lines.length === 0) {
            textarea.setCustomValidity('Loot text must contain at least one item');
            return false;
        }

        textarea.setCustomValidity('');
        return true;
    }

    // ========================================
    // Tooltips
    // ========================================

    function initializeTooltips() {
        // Initialize Bootstrap tooltips if available
        if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
            const tooltipTriggerList = [].slice.call(
                document.querySelectorAll('[data-bs-toggle="tooltip"]')
            );
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
        }
    }

    // ========================================
    // Confirm Dialogs
    // ========================================

    function initializeConfirmDialogs() {
        // Add confirmation to delete and dangerous actions
        const confirmLinks = document.querySelectorAll('a[data-confirm], button[data-confirm]');

        confirmLinks.forEach(function (element) {
            element.addEventListener('click', function (e) {
                const message = this.dataset.confirm || 'Are you sure?';
                if (!confirm(message)) {
                    e.preventDefault();
                    return false;
                }
            });
        });
    }

    // ========================================
    // Loot Text Character Counter
    // ========================================

    function initializeLootTextCounter() {
        const lootTextArea = document.querySelector('textarea[name="raw_loot_text"]');
        if (!lootTextArea) return;

        const counter = document.createElement('small');
        counter.className = 'form-text text-muted d-block mt-2';
        counter.id = 'loot-text-counter';
        lootTextArea.parentNode.appendChild(counter);

        function updateCounter() {
            const text = lootTextArea.value;
            const lines = text.split('\n').filter(function (line) {
                return line.trim().length > 0;
            });
            counter.textContent = lines.length + ' items detected';
        }

        lootTextArea.addEventListener('input', updateCounter);
        updateCounter();
    }

    // ========================================
    // Inline Payment Actions (Integrated Express Mode)
    // ========================================

    function initializeInlinePaymentActions() {
        // Copy Name buttons
        document.querySelectorAll('.copy-name-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const characterName = this.dataset.characterName;
                copyToClipboard(characterName);
                showFeedback(this, 'Name copied!');
            });
        });

        // Copy Amount buttons
        document.querySelectorAll('.copy-amount-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const amount = this.dataset.amount;
                // Remove decimals and commas for ISK transfer
                const cleanAmount = Math.floor(parseFloat(amount)).toString();
                copyToClipboard(cleanAmount);
                showFeedback(this, 'Amount copied!');
            });
        });

        // Open Window buttons (ESI)
        document.querySelectorAll('.open-window-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const payoutId = this.dataset.payoutId;
                const characterId = this.dataset.characterId;
                openCharacterWindow(payoutId, this);
            });
        });

        // Mark Verified buttons (manual override)
        document.querySelectorAll('.mark-verified-btn').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const payoutId = this.dataset.payoutId;
                markPayoutVerified(payoutId, this);
            });
        });
    }

    function copyToClipboard(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).catch(function (err) {
                console.error('Failed to copy:', err);
                fallbackCopy(text);
            });
        } else {
            fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
        } catch (err) {
            console.error('Fallback copy failed:', err);
        }
        document.body.removeChild(textarea);
    }

    function showFeedback(element, message) {
        const originalHTML = element.innerHTML;
        element.innerHTML = '<i class="fas fa-check"></i>';
        element.classList.add('btn-success');
        element.classList.remove('btn-outline-primary', 'btn-outline-info');

        setTimeout(function () {
            element.innerHTML = originalHTML;
            element.classList.remove('btn-success');
            if (element.classList.contains('copy-name-btn') || element.classList.contains('copy-amount-btn')) {
                element.classList.add('btn-outline-primary');
            } else {
                element.classList.add('btn-outline-info');
            }
        }, 1000);
    }

    function openCharacterWindow(payoutId, button) {
        const csrftoken = getCookie('csrftoken');
        const originalHTML = button.innerHTML;

        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        fetch('/payout/api/payouts/' + payoutId + '/open-window/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json',
            },
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                button.innerHTML = originalHTML;
                button.disabled = false;

                if (result.ok && result.data.success) {
                    showFeedback(button, 'Window opened!');
                } else {
                    alert('Failed to open window: ' + (result.data.error || 'Unknown error'));
                }
            })
            .catch(function (error) {
                button.innerHTML = originalHTML;
                button.disabled = false;
                console.error('Error opening window:', error);
                alert('Failed to open window: ' + error.message);
            });
    }

    function markPayoutVerified(payoutId, button) {
        if (!confirm('Mark this payout as verified? This will allow fleet finalization even without ESI verification.')) {
            return;
        }

        const csrftoken = getCookie('csrftoken');
        const buttonGroup = button.closest('.btn-group');
        const badgeContainer = button.closest('div').querySelector('.badge');
        const originalHTML = button.innerHTML;

        button.disabled = true;
        button.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

        fetch('/payout/api/payouts/' + payoutId + '/mark-verified/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json',
            },
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (result.ok && result.data.success) {
                    // Remove the button
                    button.remove();

                    // Update badge to show verified
                    if (badgeContainer) {
                        badgeContainer.className = 'badge bg-success';
                        badgeContainer.title = 'Manually verified';
                        badgeContainer.innerHTML = '<i class="fas fa-check-circle"></i> Verified';
                    }

                    showFeedback(buttonGroup, 'Marked as verified!');
                } else {
                    button.innerHTML = originalHTML;
                    button.disabled = false;
                    alert('Failed to mark as verified: ' + (result.data.error || 'Unknown error'));
                }
            })
            .catch(function (error) {
                button.innerHTML = originalHTML;
                button.disabled = false;
                console.error('Error marking as verified:', error);
                alert('Failed to mark as verified: ' + error.message);
            });
    }

    // ========================================
    // Participant Status Toggles (Scout/Exclude)
    // ========================================

    function initializeParticipantStatusToggles() {
        // Scout checkboxes
        document.querySelectorAll('.scout-checkbox').forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                updateParticipantStatus(this.dataset.participantId, 'is_scout', this.checked);
            });
        });

        // Exclude checkboxes
        document.querySelectorAll('.exclude-checkbox').forEach(function (checkbox) {
            checkbox.addEventListener('change', function () {
                updateParticipantStatus(this.dataset.participantId, 'excluded_from_payout', this.checked);
            });
        });
    }

    function updateParticipantStatus(participantId, field, value) {
        const csrftoken = getCookie('csrftoken');

        const payload = {};
        payload[field] = value;

        fetch('/payout/api/participant/' + participantId + '/update/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrftoken,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok || !result.data.success) {
                    alert('Failed to update participant: ' + (result.data.error || 'Unknown error'));
                    // Revert checkbox
                    const checkbox = document.querySelector('[data-participant-id="' + participantId + '"].' + (field === 'is_scout' ? 'scout-checkbox' : 'exclude-checkbox'));
                    if (checkbox) {
                        checkbox.checked = !value;
                    }
                }
            })
            .catch(function (error) {
                console.error('Error updating participant:', error);
                alert('Failed to update participant: ' + error.message);
            });
    }

    // ========================================
    // Copy on Click
    // ========================================

    function initializeCopyOnClick() {
        document.querySelectorAll('.copy-on-click').forEach(function (element) {
            element.addEventListener('click', function () {
                let textToCopy = this.dataset.copyText;

                // If it's an amount (contains decimal or comma), remove decimals for EVE
                if (textToCopy && textToCopy.match(/[\d,\.]/)) {
                    // Remove commas and convert to number, then floor it
                    const cleanAmount = Math.floor(parseFloat(textToCopy.replace(/,/g, '')));
                    textToCopy = cleanAmount.toString();
                }

                copyToClipboard(textToCopy);

                // Visual feedback
                const originalText = this.innerHTML;
                this.innerHTML = '<i class="fas fa-check text-success"></i> ' + originalText;

                setTimeout(function () {
                    element.innerHTML = originalText;
                }.bind(this), 1000);
            });
        });
    }

    // ========================================
    // Utility Functions
    // ========================================

    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === name + '=') {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // ========================================
    // Export for testing (optional)
    // ========================================

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = {
            formatISK: formatISK,
            validateLootText: validateLootText,
        };
    }
})();

// ========================================
// Real-time Payout Preview (Optional Enhancement)
// ========================================

function updatePayoutPreview() {
    const corpShareInput = document.querySelector('input[name="corp_share_percentage"]');
    const totalValueElement = document.querySelector('[data-total-value]');

    if (!corpShareInput || !totalValueElement) return;

    const totalValue = parseFloat(totalValueElement.dataset.totalValue || 0);
    const corpSharePercentage = parseFloat(corpShareInput.value || 0);

    const corpShare = (totalValue * corpSharePercentage) / 100;
    const participantShare = totalValue - corpShare;

    // Update display elements if they exist
    const corpShareDisplay = document.querySelector('[data-corp-share-display]');
    const participantShareDisplay = document.querySelector('[data-participant-share-display]');

    if (corpShareDisplay) {
        corpShareDisplay.textContent = corpShare.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }) + ' ISK';
    }

    if (participantShareDisplay) {
        participantShareDisplay.textContent = participantShare.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }) + ' ISK';
    }
}

// Attach to corp share input if it exists
document.addEventListener('DOMContentLoaded', function () {
    const corpShareInput = document.querySelector('input[name="corp_share_percentage"]');
    if (corpShareInput) {
        corpShareInput.addEventListener('input', updatePayoutPreview);
        updatePayoutPreview(); // Initial calculation
    }

    // Initialize participant controls (scout/exclude checkboxes)
    initializeParticipantControls();
});

// ========================================
// Participant Controls (Phase 2)
// ========================================

function initializeParticipantControls() {
    const scoutCheckboxes = document.querySelectorAll('.scout-checkbox');
    const excludeCheckboxes = document.querySelectorAll('.exclude-checkbox');

    scoutCheckboxes.forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            updateParticipantStatus(this.dataset.participantId, 'is_scout', this.checked);
        });
    });

    excludeCheckboxes.forEach(function (checkbox) {
        checkbox.addEventListener('change', function () {
            updateParticipantStatus(this.dataset.participantId, 'excluded_from_payout', this.checked);
            toggleParticipantRowStyle(this.dataset.participantId, this.checked);
        });
    });
}

function updateParticipantStatus(participantId, field, value) {
    const csrftoken = getCookie('csrftoken');

    const data = {};
    data[field] = value;

    fetch('/payout/api/participant/' + participantId + '/update/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error('Failed to update participant');
            }
            return response.json();
        })
        .then(function (data) {
            if (data.success) {
                showSuccessToast('Participant updated successfully');
            } else {
                throw new Error(data.error || 'Update failed');
            }
        })
        .catch(function (error) {
            console.error('Error updating participant:', error);
            showErrorToast('Failed to update participant: ' + error.message);
            // Revert checkbox state
            const checkbox = document.querySelector(
                '[data-participant-id="' + participantId + '"].' +
                (field === 'is_scout' ? 'scout-checkbox' : 'exclude-checkbox')
            );
            if (checkbox) {
                checkbox.checked = !value;
            }
        });
}

function toggleParticipantRowStyle(participantId, excluded) {
    const row = document.getElementById('participant-row-' + participantId);
    if (row) {
        if (excluded) {
            row.classList.add('table-secondary', 'text-muted');
        } else {
            row.classList.remove('table-secondary', 'text-muted');
        }
    }
}

function showSuccessToast(message) {
    // Simple success message (can be enhanced with Bootstrap Toast)
    console.log('SUCCESS: ' + message);
    // You can add a toast notification here if desired
}

function showErrorToast(message) {
    // Simple error message (can be enhanced with Bootstrap Toast)
    console.error('ERROR: ' + message);
    alert(message); // Fallback to alert for now
}

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + '=') {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// ========================================
// Scout Bonus Slider
// ========================================

function initializeScoutBonusSlider() {
    // Fleet detail page slider (with AJAX update)
    const slider = document.getElementById('scout-bonus-slider');
    if (slider) {
        const valueDisplay = document.getElementById('scout-bonus-value');
        const lootPoolId = slider.dataset.lootPoolId;
        let updateTimer;

        // Update display as slider moves
        slider.addEventListener('input', function () {
            if (valueDisplay) {
                valueDisplay.textContent = this.value;
            }
        });

        // Update server when slider changes (with debounce)
        slider.addEventListener('change', function () {
            clearTimeout(updateTimer);
            const newShares = this.value;

            // Show loading state
            if (valueDisplay) {
                valueDisplay.textContent = newShares + ' (updating...)';
            }

            updateTimer = setTimeout(function () {
                updateScoutBonus(lootPoolId, newShares, 'scout-bonus-value');
            }, 300);
        });
    }

    // Loot create page slider (client-side display only)
    const sliderCreate = document.getElementById('scout-bonus-slider-create');
    if (sliderCreate) {
        const valueDisplayCreate = document.getElementById('scout-bonus-value-create');

        // Update display as slider moves
        sliderCreate.addEventListener('input', function () {
            if (valueDisplayCreate) {
                valueDisplayCreate.textContent = this.value;
            }
        });
    }

    // Loot detail page slider (with AJAX update)
    const sliderDetail = document.getElementById('scout-bonus-slider-detail');
    if (sliderDetail) {
        const valueDisplayDetail = document.getElementById('scout-bonus-value-detail');
        const lootPoolIdDetail = sliderDetail.dataset.lootPoolId;
        let updateTimerDetail;

        // Update display as slider moves
        sliderDetail.addEventListener('input', function () {
            if (valueDisplayDetail) {
                valueDisplayDetail.textContent = this.value;
            }
        });

        // Update server when slider changes (with debounce)
        sliderDetail.addEventListener('change', function () {
            clearTimeout(updateTimerDetail);
            const newShares = this.value;

            // Show loading state
            if (valueDisplayDetail) {
                valueDisplayDetail.textContent = newShares + ' (updating...)';
            }

            updateTimerDetail = setTimeout(function () {
                updateScoutBonus(lootPoolIdDetail, newShares, 'scout-bonus-value-detail');
            }, 300);
        });
    }

    // Loot edit page slider (with AJAX update)
    const sliderEdit = document.getElementById('scout-bonus-slider-edit');
    if (sliderEdit) {
        const valueDisplayEdit = document.getElementById('scout-bonus-value-edit');
        const lootPoolIdEdit = sliderEdit.dataset.lootPoolId;
        let updateTimerEdit;

        // Update display as slider moves
        sliderEdit.addEventListener('input', function () {
            if (valueDisplayEdit) {
                valueDisplayEdit.textContent = this.value;
            }
        });

        // Update server when slider changes (with debounce)
        sliderEdit.addEventListener('change', function () {
            clearTimeout(updateTimerEdit);
            const newShares = this.value;

            // Show loading state
            if (valueDisplayEdit) {
                valueDisplayEdit.textContent = newShares + ' (updating...)';
            }

            updateTimerEdit = setTimeout(function () {
                updateScoutBonus(lootPoolIdEdit, newShares, 'scout-bonus-value-edit');
            }, 300);
        });
    }
}

function updateScoutBonus(lootPoolId, shares, displayElementId) {
    const csrftoken = getCookie('csrftoken');
    // Use provided displayElementId or fallback to default
    const elementId = displayElementId || 'scout-bonus-value';
    const valueDisplay = document.getElementById(elementId);

    fetch('/payout/api/loot/' + lootPoolId + '/update-scout-bonus/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ shares: shares }),
    })
        .then(function (response) {
            if (!response.ok) {
                throw new Error('Failed to update scout shares');
            }
            return response.json();
        })
        .then(function (data) {
            if (data.success) {
                // Update display
                if (valueDisplay) {
                    valueDisplay.textContent = shares;
                }
                showSuccessToast('Scout shares updated to ' + shares + '. Payouts recalculated.');

                // Reload page to show updated payouts
                setTimeout(function () {
                    window.location.reload();
                }, 1000);
            } else {
                throw new Error(data.error || 'Update failed');
            }
        })
        .catch(function (error) {
            console.error('Error updating scout shares:', error);
            showErrorToast('Failed to update scout shares: ' + error.message);
            // Reset display
            if (valueDisplay) {
                // Derive slider ID from display element ID by replacing '-value' with '-slider'
                const sliderId = elementId.replace('-value', '-slider');
                const slider = document.getElementById(sliderId);
                if (slider) {
                    valueDisplay.textContent = slider.value;
                }
            }
        });
}
