/* Boss configuration UI enhancements. */
(function () {
    const originalIsListField = window.isListField;
    window.isListField = function (path) {
        return (typeof originalIsListField === 'function' && originalIsListField(path))
            || path === 'boss.target_guilds';
    };

    if (window.CONFIG_CATEGORY_HINTS) {
        window.CONFIG_CATEGORY_HINTS.boss = 'Auto-join Boss battles in selected guilds';
    }

    const style = document.createElement('style');
    style.textContent = `
        .boss-target-help {
            margin: -4px 0 10px;
            color: #8b93a7;
            font-size: .82rem;
            line-height: 1.45;
        }
        .boss-target-help strong { color: var(--primary); }
        .boss-target-tags { min-height: 34px; }
    `;
    document.head.appendChild(style);

    const originalRenderListInput = window.renderListInput;
    window.renderListInput = function (path, v, parentEnabled = true) {
        if (path !== 'boss.target_guilds') {
            return typeof originalRenderListInput === 'function'
                ? originalRenderListInput(path, v, parentEnabled)
                : '';
        }

        const items = Array.isArray(v)
            ? [...v]
            : (v && String(v).trim()
                ? String(v).split(',').map(s => s.trim()).filter(Boolean)
                : []);
        const tags = items.map((item, i) => `
            <span class="cfg-tag">
                <span class="cfg-tag-text">${item}</span>
                <button type="button" class="cfg-tag-remove" onclick="removeListItem('${path}', ${i}, event)" aria-label="Remove">×</button>
            </span>
        `).join('');
        const dis = parentEnabled ? '' : ' disabled';

        return `
            <div class="cfg-list-input boss-target-input" data-path="${path}">
                <div class="boss-target-help">
                    Enter the <strong>Guild ID</strong> where Boss battles should be joined automatically.
                    Only these guilds are eligible; <strong>Ignore Guilds</strong> still takes priority.
                </div>
                <div class="cfg-tags boss-target-tags">
                    ${tags || '<span class="cfg-tags-empty">No target guilds configured</span>'}
                </div>
                <div class="cfg-list-add">
                    <div class="cfg-input-wrap cfg-input-wrap-sm">
                        <input type="text" inputmode="numeric" class="cfg-input"
                            placeholder="Paste Guild ID and press Enter"
                            data-list-input="${path}"${dis}
                            onkeydown="if(event.key==='Enter'){addListItem('${path}', this, event);}">
                    </div>
                    <button type="button" class="cfg-add-btn" ${parentEnabled ? `onclick="addListItem('${path}', this.previousElementSibling.querySelector('input'), event)"` : 'disabled'}>Add Guild</button>
                </div>
            </div>
        `;
    };
})();
