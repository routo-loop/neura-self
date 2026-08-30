/* 

# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.



*/

/*
 * Send OWOCash — Dashboard side of the cash-transfer feature.
 *
 * Flow:
 *   Dashboard account card -> "Send OWOCash to this account"
 *       -> SendCashDialog (destination + amount + all accounts & balances)
 *       -> BalanceValidation (inline + server-side via /api/send_owocash/preview)
 *       -> optional insufficient-balance confirmation
 *       -> POST /api/send_owocash  (TransferCoordinator runs the bot flow)
 *       -> poll /api/send_owocash/status until complete -> results
 *
 * English-only UI. Reuses the existing modal (.proxy-modal), button
 * (.btn-control), toast and list design tokens.
 */

window.sendCashState = {
    destinationId: null,
    destinationName: '',
    eligibleIds: [],
    operationId: null,
    pollTimer: null,
    sending: false
};

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function showSendCashError(message) {
    const errorEl = document.getElementById('send-cash-amount-error');
    if (errorEl) {
        errorEl.textContent = message;
        errorEl.hidden = false;
    }
}

function hideSendCashError() {
    const errorEl = document.getElementById('send-cash-amount-error');
    if (errorEl) errorEl.hidden = true;
}

function validateSendCashAmount() {
    const el = document.getElementById('send-cash-amount');
    if (!el) return null;
    const raw = (el.value || '').trim();
    if (!raw) {
        showSendCashError('Please enter a cash amount.');
        return null;
    }
    if (!/^[0-9]+$/.test(raw)) {
        showSendCashError('Amount must be a whole number greater than zero.');
        return null;
    }
    const num = Number(raw);
    if (!Number.isFinite(num) || Number.isNaN(num)) {
        showSendCashError('Amount must be a valid number.');
        return null;
    }
    if (num <= 0) {
        showSendCashError('Amount must be greater than zero.');
        return null;
    }
    if (!Number.isInteger(num)) {
        showSendCashError('Amount must be a whole number.');
        return null;
    }
    hideSendCashError();
    return num;
}

function sendCashAccountRow(acc, amount, isDestination) {
    const known = acc.cash_known !== false && typeof acc.cash === 'number' && !isNaN(acc.cash);
    const balanceText = known ? acc.cash.toLocaleString() + ' OWOCash' : 'Unknown';
    const eligible = amount > 0 && known && acc.cash >= amount;
    const insufficient = amount > 0 && known && acc.cash < amount;

    let rowClass = 'send-cash-account-row';
    if (isDestination) rowClass += ' destination';
    else if (amount > 0) rowClass += eligible ? ' eligible' : (insufficient ? ' insufficient' : '');

    const badge = isDestination ? '<span class="send-cash-badge">Destination</span>' : '';
    const tag = !isDestination && amount > 0
        ? (eligible ? '<span class="send-cash-eligible-tag">Ready</span>' : (insufficient ? '<span class="send-cash-insufficient-tag">Insufficient</span>' : ''))
        : '';

    return `
        <div class="${rowClass}">
            <div class="send-cash-account-name">
                <span class="send-cash-account-username">${escapeHtml(acc.username)}</span>
                ${badge}${tag}
            </div>
            <div class="send-cash-account-balance">${balanceText}</div>
        </div>
    `;
}

function computeSendCashBuckets(amount) {
    const st = window.sendCashState;
    const accounts = (Array.isArray(accountsList) ? accountsList : []).filter(a => String(a.id) !== String(st.destinationId));
    const eligible = [];
    const insufficient = [];
    const unknown = [];
    for (const acc of accounts) {
        const known = acc.cash_known !== false && typeof acc.cash === 'number' && !isNaN(acc.cash);
        if (!known) unknown.push(acc);
        else if (acc.cash < amount) insufficient.push(acc);
        else eligible.push(acc);
    }
    return { eligible, insufficient, unknown };
}

function renderSendCashAccounts() {
    const list = document.getElementById('send-cash-accounts');
    if (!list) return;
    const el = document.getElementById('send-cash-amount');
    const raw = el ? (el.value || '').trim() : '';
    const amount = raw && /^[0-9]+$/.test(raw) ? Number(raw) : 0;
    const accounts = Array.isArray(accountsList) ? accountsList : [];
    if (!accounts.length) {
        list.innerHTML = '<div class="no-data">No accounts online. Start the bot to see connected accounts here.</div>';
        return;
    }
    list.innerHTML = accounts
        .map(acc => sendCashAccountRow(acc, amount, String(acc.id) === String(window.sendCashState.destinationId)))
        .join('');
    updateSendCashSummary(amount);
}

function updateSendCashSummary(amount) {
    const summary = document.getElementById('send-cash-summary');
    if (!summary) return;
    if (!amount || amount <= 0) {
        summary.innerHTML = 'Enter an amount to check which accounts can send.';
        return;
    }
    const { eligible, insufficient, unknown } = computeSendCashBuckets(amount);
    window.sendCashState.eligibleIds = eligible.map(a => a.id);
    const parts = [];
    parts.push('<b>' + eligible.length + '</b> account' + (eligible.length === 1 ? '' : 's') + ' ready to send.');
    if (insufficient.length) {
        parts.push('<b>' + insufficient.length + '</b> with insufficient balance.');
    }
    if (unknown.length) {
        parts.push('<b>' + unknown.length + '</b> with unsynced balance.');
    }
    if (!eligible.length) {
        parts.push('<span style="color:var(--danger)">No eligible source accounts.</span>');
    }
    summary.innerHTML = parts.join(' &nbsp;&middot;&nbsp; ');
}

window.refreshOpenSendCashModal = function() {
    const st = window.sendCashState;
    if (!st.destinationId) return;
    const modal = document.getElementById('send-cash-modal');
    if (modal && modal.classList.contains('visible')) {
        renderSendCashAccounts();
    }
};

window.openSendCashModal = function(destinationId) {
    const acc = (accountsList || []).find(a => String(a.id) === String(destinationId));
    if (!acc) {
        showToast('Destination account not found.', 'error');
        return;
    }
    const st = window.sendCashState;
    if (st.sending) return;

    st.destinationId = String(destinationId);
    st.destinationName = acc.username;
    st.operationId = null;
    window.clearInterval(st.pollTimer);
    st.pollTimer = null;

    const modal = document.getElementById('send-cash-modal');
    const destName = document.getElementById('send-cash-destination-name');
    const destId = document.getElementById('send-cash-destination-id');
    const amountInput = document.getElementById('send-cash-amount');
    const sendBtn = document.getElementById('send-cash-send-btn');
    const view = document.getElementById('send-cash-view');
    if (view) view.classList.remove('hidden');
    const busy = document.getElementById('send-cash-busy');
    if (busy) busy.classList.add('hidden');
    const results = document.getElementById('send-cash-results');
    if (results) results.classList.add('hidden');
    if (destName) destName.textContent = acc.username;
    if (destId) destId.textContent = acc.id;
    if (amountInput) amountInput.value = '';
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Send'; }
    hideSendCashError();
    if (modal) modal.classList.add('visible');
    renderSendCashAccounts();
    if (amountInput) amountInput.focus();
};

window.closeSendCashModal = function() {
    const st = window.sendCashState;
    if (st.sending) return;
    window.clearInterval(st.pollTimer);
    st.pollTimer = null;
    const modal = document.getElementById('send-cash-modal');
    if (modal) modal.classList.remove('visible');
};

window.cancelSendCash = function() {
    closeSendCashModal();
};

window.onSendCashAmountInput = function() {
    validateSendCashAmount();
    renderSendCashAccounts();
};

function setSendCashBusy(busy) {
    const sendBtn = document.getElementById('send-cash-send-btn');
    const cancelBtn = document.getElementById('send-cash-cancel-btn');
    const busyEl = document.getElementById('send-cash-busy');
    const view = document.getElementById('send-cash-view');
    window.sendCashState.sending = busy;
    if (sendBtn) { sendBtn.disabled = busy; sendBtn.textContent = busy ? 'Sending…' : 'Send'; }
    if (cancelBtn) cancelBtn.disabled = busy;
    if (busyEl) busyEl.classList.toggle('hidden', !busy);
    if (view) view.classList.toggle('hidden', busy);
}

function buildSendCashConfirmList(insufficient) {
    if (!insufficient || !insufficient.length) {
        return '<div class="no-data">No insufficient accounts.</div>';
    }
    return insufficient.map(a => {
        const balance = (a.cash_known !== false && typeof a.cash === 'number') ? a.cash.toLocaleString() + ' OWOCash' : 'Unknown';
        return `<div class="send-cash-confirm-row">
                    <span class="send-cash-confirm-name">${escapeHtml(a.username)}</span>
                    <span class="send-cash-confirm-balance">Balance: ${balance}</span>
                </div>`;
    }).join('');
}

function buildSendCashResultsHtml(operation) {
    const totals = operation.totals || { success: 0, failed: 0, skipped: 0, total_sent: 0 };
    const rows = Object.entries(operation.results || {}).map(([aid, res]) => {
        const acc = (accountsList || []).find(a => String(a.id) === String(aid));
        const username = acc ? acc.username : aid;
        const statusText = res.status === 'success'
            ? 'Sent'
            : res.status === 'failed'
                ? 'Failed'
                : 'Skipped';
        const statusClass = res.status === 'success'
            ? 'send-cash-result-ok'
            : res.status === 'failed'
                ? 'send-cash-result-fail'
                : 'send-cash-result-skip';
        const reason = res.reason ? `<span class="send-cash-result-reason">${escapeHtml(res.reason)}</span>` : '';
        return `<div class="send-cash-result-row ${statusClass}">
                    <span class="send-cash-result-name">${escapeHtml(username)}</span>
                    <span class="send-cash-result-status">${statusText}${reason}</span>
                </div>`;
    }).join('');

    return `
        <div class="send-cash-results-summary">
            <div><b>Successful:</b> ${totals.success}</div>
            <div><b>Skipped:</b> ${totals.skipped}</div>
            <div><b>Failed:</b> ${totals.failed}</div>
            <div><b>Total OWOCash sent:</b> ${Number(totals.total_sent || 0).toLocaleString()}</div>
        </div>
        <div class="send-cash-result-list">${rows}</div>
    `;
}

window.showSendCashInsufficientConfirm = function() {
    const modal = document.getElementById('send-cash-confirm-modal');
    const list = document.getElementById('send-cash-confirm-list');
    const text = document.getElementById('send-cash-confirm-text');
    const skipCount = document.getElementById('send-cash-confirm-skip-count');
    const proceedCount = document.getElementById('send-cash-confirm-proceed-count');
    if (!modal) return;
    const amount = validateSendCashAmount();
    if (amount == null) return;
    const { eligible, insufficient, unknown } = computeSendCashBuckets(amount);
    if (list) list.innerHTML = buildSendCashConfirmList(insufficient);
    if (text) {
        const parts = [];
        parts.push('<b>Requested amount:</b> ' + Number(amount).toLocaleString() + ' OWOCash');
        if (unknown.length) {
            parts.push('<span style="color:var(--text-muted)">' + unknown.length + ' account(s) with unsynced balance will also be skipped.</span>');
        }
        text.innerHTML = parts.join('<br>');
    }
    if (skipCount) {
        const skippedTotal = insufficient.length + unknown.length;
        skipCount.textContent = skippedTotal + (skippedTotal === 1 ? ' account will' : ' accounts will') + ' be skipped.';
    }
    if (proceedCount) {
        proceedCount.textContent = eligible.length + (eligible.length === 1 ? ' account will' : ' accounts will') + ' proceed.';
    }
    modal.classList.add('visible');
};

window.hideSendCashInsufficientConfirm = function() {
    const modal = document.getElementById('send-cash-confirm-modal');
    if (modal) modal.classList.remove('visible');
};

window.continueSendCash = function() {
    hideSendCashInsufficientConfirm();
    const amount = validateSendCashAmount();
    if (amount == null) return;
    const st = window.sendCashState;
    const { eligible } = computeSendCashBuckets(amount);
    if (!eligible.length) {
        showToast('No eligible source accounts to send from.', 'error');
        return;
    }
    window.sendCashStartOperation(amount, eligible.map(a => a.id));
};

window.cancelSendCashContinue = function() {
    hideSendCashInsufficientConfirm();
};

window.submitSendCash = async function() {
    const st = window.sendCashState;
    if (st.sending) return;
    const amount = validateSendCashAmount();
    if (amount == null) return;

    // Server-side validation of every managed account against the amount.
    try {
        const res = await fetch('/api/send_owocash/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ destination_id: st.destinationId, amount })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            showSendCashError(data.error || 'Unable to validate balances.');
            return;
        }
        const eligible = (data.eligible || []).map(a => a.id);
        if (!eligible.length) {
            showToast('No eligible source accounts to send from.', 'error');
            return;
        }
        if (data.insufficient && data.insufficient.length > 0) {
            showSendCashInsufficientConfirm();
            return;
        }
        await window.sendCashStartOperation(amount, eligible);
    } catch (e) {
        showSendCashError('Network error while validating balances.');
    }
};

window.sendCashStartOperation = async function(amount, accountIds) {
    const st = window.sendCashState;
    if (st.sending) return;
    const resultView = document.getElementById('send-cash-results');
    const resultText = document.getElementById('send-cash-results-text');
    if (resultView) resultView.classList.add('hidden');
    if (resultText) resultText.innerHTML = '';
    setSendCashBusy(true);

    try {
        const res = await fetch('/api/send_owocash', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                destination_id: st.destinationId,
                amount: amount,
                account_ids: accountIds
            })
        });
        const data = await res.json();
        if (!res.ok || !data.success) {
            setSendCashBusy(false);
            showSendCashError(data.error || 'Failed to start the transfer.');
            return;
        }
        st.operationId = data.operation_id;
        renderSendCashProgress(0, 0, 'Starting transfer…');
        window.clearInterval(st.pollTimer);
        st.pollTimer = window.setInterval(() => pollSendCashStatus(), 1500);
        await pollSendCashStatus();
    } catch (e) {
        setSendCashBusy(false);
        showSendCashError('Network error while starting the transfer.');
    }
};

async function pollSendCashStatus() {
    const st = window.sendCashState;
    if (!st.operationId || !st.sending) return;
    try {
        const res = await fetch('/api/send_owocash/status?op_id=' + encodeURIComponent(st.operationId));
        const data = await res.json();
        if (!res.ok || !data.success) {
            setSendCashBusy(false);
            showToast('Unable to read transfer status.', 'error');
            return;
        }
        const op = data.operation;
        renderSendCashProgress(op.progress, op.status, null);
        if (op.status === 'completed' || op.status === 'failed' || op.status === 'cancelled') {
            window.clearInterval(st.pollTimer);
            st.pollTimer = null;
            finishSendCashOperation(op);
        }
    } catch (e) {
        // keep polling — transient network errors should not kill the job
    }
}

function renderSendCashProgress(progress, status, extraText) {
    const bar = document.getElementById('send-cash-progress-bar');
    const label = document.getElementById('send-cash-progress-label');
    if (bar) bar.style.width = Math.max(0, Math.min(100, progress || 0)) + '%';
    let text = extraText || 'Processing… ' + (progress || 0) + '%';
    if (status === 'failed') text = extraText || 'Operation failed.';
    if (label) label.textContent = text;
}

function finishSendCashOperation(op) {
    const st = window.sendCashState;
    setSendCashBusy(false);

    const view = document.getElementById('send-cash-view');
    const resultView = document.getElementById('send-cash-results');
    const resultText = document.getElementById('send-cash-results-text');
    const sendBtn = document.getElementById('send-cash-send-btn');
    if (view) view.classList.add('hidden');
    if (resultView) resultView.classList.remove('hidden');

    const totals = op.totals || {};
    if (op.status === 'failed') {
        if (resultText) resultText.innerHTML = '<div class="no-data">' + escapeHtml(op.error || 'The operation failed.') + '</div>';
    } else {
        let html = '';
        if ((totals.failed || 0) > 0 && (totals.success || 0) === 0) {
            html += '<div class="send-cash-all-failed">All attempted transfers failed. No OWOCash was sent.</div>';
        }
        html += buildSendCashResultsHtml(op);
        if (resultText) resultText.innerHTML = html;
    }
    if (sendBtn) { sendBtn.disabled = false; sendBtn.textContent = 'Done'; }

    window.fetchAccounts();
    window.refreshOpenSendCashModal();
}

window.closeSendCashResults = function() {
    const st = window.sendCashState;
    setSendCashBusy(false);
    closeSendCashModal();
};