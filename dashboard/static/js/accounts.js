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

window.fetchAccounts = async function() {
    console.log("Fetching accounts...");
    try {
        const res = await fetch('/api/accounts/list');
        const data = await res.json();
        console.log(`Fetched ${data.length} accounts`);
        accountsList = data;
        if (data.length > 0) {
            if (!currentAccountId || !data.find(a => a.id === currentAccountId)) {
                currentAccountId = data[0].id;
            }
        }
        renderAccountGrid();
        updateGlobalAccountName(); 
    } catch (e) {
        console.error("Failed to fetch accounts", e);
        const grid = document.getElementById('accounts-grid');
        if (grid) grid.innerHTML = `<div class="no-data error">Error fetching accounts: ${e.message}</div>`;
    }
};

function updateGlobalAccountName() {
    const nameEl = document.getElementById('currentAccountName');
    if (!nameEl) return;
    if (currentAccountId) {
        const acc = accountsList.find(a => a.id === currentAccountId);
        if (acc) {
            nameEl.innerText = `ACCOUNT: ${acc.username}`;
            return;
        }
    }
    nameEl.innerText = 'Loading account...';
}

window.selectAccount = function(id) {
    console.log(`Selecting account: ${id}`);
    currentAccountId = id;
    renderAccountGrid();
    const acc = accountsList.find(a => a.id === id);
    if (acc) {
        showToast(`Switched to account: ${acc.username}`, 'success');
        updateGlobalAccountName(); 
    }
    if (lineChart) lineChart.data.datasets[0].data = Array(30).fill(0);
    const configView = document.getElementById('config');
    if (configView && configView.classList.contains('active-view')) loadConfig();
    update();
    const dashNav = document.querySelector('.nav-item[onclick*="dash"]');
    if (dashNav) nav('dash', dashNav);
};

function renderAccountGrid() {
    const grid = document.getElementById('accounts-grid');
    if (!grid) return;
    if (!accountsList || !accountsList.length) {
        grid.innerHTML = '<div class="no-data">No accounts online. Start the bot to see connected accounts here.</div>';
        return;
    }
    grid.innerHTML = accountsList.map(acc => {
        const isSelected = acc.id === currentAccountId;
        const statusClass = acc.paused ? 'paused' : 'running';
        const statusLabel = acc.paused ? 'Paused' : 'Running';
        const avatar = acc.avatar
            ? `<img src="${acc.avatar}" class="account-avatar-lg" alt="">`
            : `<span class="icon-svg account-avatar-lg account-avatar-fallback" style="--icon: url('/static/assets/neura_icons/discord.svg');"></span>`;
        return `
            <div class="account-picker-card ${isSelected ? 'selected' : ''}" onclick="selectAccount('${acc.id}')" role="button" tabindex="0">
                <div class="account-card-top">
                    ${avatar}
                    <div class="account-card-meta">
                        <div class="account-card-name">${acc.username}</div>
                        <div class="account-card-id">User ID · ${acc.id}</div>
                        <div class="account-card-status ${statusClass}">${statusLabel}</div>
                    </div>
                    ${isSelected ? '<span class="account-selected-badge">Selected</span>' : ''}
                </div>
                <div class="account-card-stats">
                    <div class="account-stat">
                        <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/coins.svg');"></span>
                        <div class="account-stat-val">${(acc.cash || 0).toLocaleString()}</div>
                        <div class="account-stat-lbl">Balance</div>
                    </div>
                    <div class="account-stat">
                        <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/terminal.svg');"></span>
                        <div class="account-stat-val">${acc.session_total || 0}</div>
                        <div class="account-stat-lbl">Session Cmds</div>
                    </div>
                    <div class="account-stat">
                        <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/bolt.svg');"></span>
                        <div class="account-stat-val">${acc.gems_used || 0}</div>
                        <div class="account-stat-lbl">Gems Used</div>
                    </div>
                </div>
                ${isSelected ? `<button type="button" class="send-cash-open-btn" onclick="event.stopPropagation(); window.openSendCashModal('${acc.id}')">
                    <span class="icon-svg" style="--icon: url('/static/assets/neura_icons/money.svg');"></span>
                    <span class="btn-text">Send OWOCash to this account</span>
                </button>` : ''}
            </div>
        `;
    }).join('');
}

window.fetchAccountConfig = async function() {
    try {
        const res = await fetch('/api/accounts/config');
        const data = await res.json();
        accountConfigList = data.accounts || [];
        renderAccountConfigList();
    } catch (e) {
        console.error('Failed to fetch account config', e);
    }
};

function renderAccountConfigList() {
    const el = document.getElementById('account-config-list');
    if (!el) return;
    if (!accountConfigList.length) {
        el.innerHTML = '<div class="no-data">No accounts configured. Click Add Account.</div>';
        return;
    }
    el.innerHTML = accountConfigList.map((acc, i) => {
        const token = acc.token_masked || '••••••';
        const proxy = acc.proxy_id ? `Proxy: ${acc.proxy_id}` : 'Direct';
        const status = acc.enabled !== false ? 'Enabled' : 'Disabled';
        return `
            <div class="account-config-card">
                <div class="account-config-info">
                    <strong>${acc.name || 'Unnamed'}</strong>
                    <span class="mono">${token}</span>
                    <span class="dim">${proxy} · ${status}</span>
                </div>
                <div class="account-config-actions">
                    <button class="btn-proxy-sm" onclick="editAccountConfig(${i})">Edit</button>
                    <button class="btn-proxy-sm danger" onclick="deleteAccountConfig(${i})">Del</button>
                </div>
            </div>
        `;
    }).join('');
}

window.showAccountForm = function(index = -1) {
    const modal = document.getElementById('account-form-modal');
    const title = document.getElementById('acct-form-title');
    document.getElementById('acct-form-index').value = index;
    if (index >= 0 && accountConfigList[index]) {
        const acc = accountConfigList[index];
        title.textContent = 'Edit Account';
        document.getElementById('acct-form-name').value = acc.name || '';
        document.getElementById('acct-form-token').value = '';
        document.getElementById('acct-form-token').placeholder = acc.token_masked ? 'Leave blank to keep current token' : 'Discord user token';
        document.getElementById('acct-form-channels').value = (acc.channels || []).join(' ');
        document.getElementById('acct-form-enabled').checked = acc.enabled !== false;
        if (typeof populateAccountProxyDropdown === 'function') populateAccountProxyDropdown();
        document.getElementById('acct-form-proxy').value = acc.proxy_id || '';
    } else {
        title.textContent = 'Add Account';
        document.getElementById('acct-form-name').value = '';
        document.getElementById('acct-form-token').value = '';
        document.getElementById('acct-form-token').placeholder = 'Discord user token';
        document.getElementById('acct-form-channels').value = '';
        document.getElementById('acct-form-enabled').checked = true;
        if (typeof populateAccountProxyDropdown === 'function') populateAccountProxyDropdown();
        document.getElementById('acct-form-proxy').value = '';
    }
    if (modal) modal.classList.add('visible');
};

window.hideAccountForm = function() {
    const modal = document.getElementById('account-form-modal');
    if (modal) modal.classList.remove('visible');
};

window.editAccountConfig = function(index) {
    showAccountForm(index);
};

window.deleteAccountConfig = async function(index) {
    if (!confirm('Remove this account from config?')) return;
    accountConfigList.splice(index, 1);
    await saveAccountConfigList();
};

window.saveAccountForm = async function() {
    const index = parseInt(document.getElementById('acct-form-index').value, 10);
    const name = document.getElementById('acct-form-name').value.trim();
    const token = document.getElementById('acct-form-token').value.trim();
    const channels = document.getElementById('acct-form-channels').value.trim().split(/\s+/).filter(Boolean);
    const proxy_id = document.getElementById('acct-form-proxy').value || null;
    const enabled = document.getElementById('acct-form-enabled').checked;
    if (!name) {
        showToast('Account name is required', 'error');
        return;
    }
    const entry = { name, channels, enabled, proxy_id };
    if (index >= 0 && accountConfigList[index]) {
        entry.token = accountConfigList[index].token;
        if (token) entry.token = token;
        if (!entry.token) {
            showToast('Token is required for new accounts', 'error');
            return;
        }
        accountConfigList[index] = entry;
    } else {
        if (!token) {
            showToast('Token is required', 'error');
            return;
        }
        entry.token = token;
        accountConfigList.push(entry);
    }
    await saveAccountConfigList();
    hideAccountForm();
};

async function saveAccountConfigList() {
    try {
        const res = await fetch('/api/accounts/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ accounts: accountConfigList }),
        });
        const data = await res.json();
        if (data.status === 'success') {
            showToast('Accounts saved — restart bot to apply', 'success');
            await fetchAccountConfig();
        } else {
            showToast(data.message || 'Save failed', 'error');
        }
    } catch (e) {
        showToast('Save failed', 'error');
    }
}