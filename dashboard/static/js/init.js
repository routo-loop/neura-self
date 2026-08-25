/*

# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

*/

function initConfigSearch() {
    const input = document.getElementById('config-search');
    if (!input) return;
    input.addEventListener('input', () => filterConfigSearch(input.value));
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') clearConfigSearch();
    });
}

function updateMobileControls() {
    const mobileControls = document.getElementById('mobileControls');
    if (!mobileControls) return;
    const isDashboard = document.getElementById('dash').classList.contains('active-view');
    if (isDashboard && window.innerWidth <= 768) {
        mobileControls.style.display = 'flex';
    } else {
        mobileControls.style.display = 'none';
    }
}

function loadBossUiEnhancements() {
    return new Promise((resolve) => {
        if (window.__bossUiLoaded) return resolve();
        const script = document.createElement('script');
        script.src = '/static/js/boss_ui.js?v=1.0.0';
        script.onload = () => {
            window.__bossUiLoaded = true;
            resolve();
        };
        script.onerror = () => {
            console.warn('Boss UI enhancements failed to load; using standard configuration UI.');
            resolve();
        };
        document.head.appendChild(script);
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    console.log("DOM Content Loaded - Initializing...");
    initDashCharts();
    window.fetchAccounts();
    if (typeof fetchProxies === 'function') fetchProxies();
    fetchAccountConfig();
    await loadBossUiEnhancements();
    loadConfig();
    initDynamicTilt();
    initConfigSearch();
    setInterval(window.fetchAccounts, 5000);
    setInterval(update, 1000);
    setInterval(window.pollForCaptchas, 2000);
    updateMobileControls();
    window.addEventListener('resize', updateMobileControls);
});
