import { app } from "../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// Cache for trigger words
const triggerCache = {};

// Inject custom CSS
function injectStyles() {
    if (document.getElementById("power-lora-styles")) return;

    const style = document.createElement("style");
    style.id = "power-lora-styles";
    style.textContent = `
        .power-lora-container {
            padding: 10px;
            font-family: Arial, sans-serif;
        }
        .power-lora-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
            padding: 6px 8px;
            background: rgba(40, 40, 45, 0.8);
            border-radius: 6px;
        }
        .power-lora-row.disabled {
            opacity: 0.5;
        }
        .power-lora-toggle {
            position: relative;
            width: 32px;
            height: 18px;
            background: #555;
            border-radius: 9px;
            cursor: pointer;
            transition: background 0.2s;
            flex-shrink: 0;
        }
        .power-lora-toggle.on {
            background: #2ecc71;
        }
        .power-lora-toggle::after {
            content: '';
            position: absolute;
            width: 14px;
            height: 14px;
            background: #fff;
            border-radius: 50%;
            top: 2px;
            left: 2px;
            transition: left 0.2s;
        }
        .power-lora-toggle.on::after {
            left: 16px;
        }
        .power-lora-select {
            flex: 1;
            background: #2a2a2e;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 4px 8px;
            color: #fff;
            font-size: 11px;
            cursor: pointer;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .power-lora-select:hover {
            border-color: #666;
        }
        .power-lora-strength {
            width: 50px;
            background: #2a2a2e;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 4px 6px;
            color: #fff;
            font-size: 11px;
            text-align: center;
        }
        .power-lora-strength:focus {
            outline: none;
            border-color: #7aa2f7;
        }
        .power-lora-delete {
            background: #c0392b;
            border: none;
            border-radius: 4px;
            color: #fff;
            width: 22px;
            height: 22px;
            cursor: pointer;
            font-size: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        .power-lora-delete:hover {
            background: #e74c3c;
        }
        .power-lora-trigger {
            background: rgba(122, 162, 247, 0.2);
            color: #7aa2f7;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 10px;
            max-width: 80px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .power-lora-add {
            background: #27ae60;
            border: none;
            border-radius: 6px;
            color: #fff;
            padding: 8px 16px;
            cursor: pointer;
            font-size: 12px;
            font-weight: bold;
            width: 100%;
            margin-top: 8px;
        }
        .power-lora-add:hover {
            background: #2ecc71;
        }
        .power-lora-dropdown {
            position: fixed;
            background: #2a2a2e;
            border: 1px solid #555;
            border-radius: 6px;
            max-height: 300px;
            overflow-y: auto;
            z-index: 999999;
            box-shadow: 0 8px 24px rgba(0,0,0,0.6);
        }
        .power-lora-dropdown-search {
            padding: 8px;
            border-bottom: 1px solid #444;
            position: sticky;
            top: 0;
            background: #2a2a2e;
        }
        .power-lora-dropdown-search input {
            width: 100%;
            background: #1a1a1e;
            border: 1px solid #444;
            border-radius: 4px;
            padding: 6px 10px;
            color: #fff;
            font-size: 12px;
            box-sizing: border-box;
        }
        .power-lora-dropdown-search input:focus {
            outline: none;
            border-color: #7aa2f7;
        }
        .power-lora-dropdown-item {
            padding: 8px 12px;
            cursor: pointer;
            font-size: 11px;
            color: #ccc;
            border-bottom: 1px solid #333;
        }
        .power-lora-dropdown-item:hover {
            background: #3a3a3e;
            color: #fff;
        }
        .power-lora-dropdown-item:last-child {
            border-bottom: none;
        }
    `;
    document.head.appendChild(style);
}

app.registerExtension({
    name: "BoudoirPromptLibrary.PowerLoRAWidget",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "PowerLoRALoaderWithTriggers") {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function() {
            onNodeCreated?.apply(this, arguments);

            const node = this;
            node.loraRows = [];
            node.loraList = [];
            node.triggerDisplays = {};

            // Hide the lora_data widget
            setTimeout(() => {
                injectStyles();
                hideDataWidget(node);
                loadLoraList(node).then(() => {
                    createUI(node);
                });
            }, 100);
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            onConfigure?.apply(this, arguments);
            setTimeout(() => {
                injectStyles();
                hideDataWidget(this);
                loadLoraList(this).then(() => {
                    parseLoraData(this);
                    createUI(this);
                });
            }, 200);
        };
    }
});

function hideDataWidget(node) {
    if (!node.widgets) return;

    for (const widget of node.widgets) {
        if (widget.name === "lora_data") {
            widget.computeSize = () => [0, -4];
            widget.type = "hidden";
        }
    }
}

async function loadLoraList(node) {
    try {
        const response = await fetch("/object_info");
        if (response.ok) {
            const data = await response.json();
            // Find any node that has lora_name input
            for (const [nodeName, nodeInfo] of Object.entries(data)) {
                if (nodeInfo.input?.required?.lora_name) {
                    node.loraList = nodeInfo.input.required.lora_name[0] || [];
                    break;
                }
            }
        }
    } catch (e) {
        console.log("[PowerLoRA] Error loading lora list:", e);
    }

    if (!node.loraList.length) {
        node.loraList = ["None"];
    }
}

function parseLoraData(node) {
    const widget = node.widgets?.find(w => w.name === "lora_data");
    if (!widget?.value || widget.value === "[]") {
        node.loraRows = [];
        return;
    }

    try {
        node.loraRows = JSON.parse(widget.value);
    } catch (e) {
        console.log("[PowerLoRA] Error parsing lora_data:", e);
        node.loraRows = [];
    }
}

function syncToWidget(node) {
    const widget = node.widgets?.find(w => w.name === "lora_data");
    if (widget) {
        widget.value = JSON.stringify(node.loraRows);
    }
    if (node.graph) {
        node.graph.setDirtyCanvas(true, true);
    }
}

function createUI(node) {
    // Remove existing UI if any
    if (node.powerLoraContainer) {
        node.powerLoraContainer.remove();
    }

    const container = document.createElement("div");
    container.className = "power-lora-container";
    node.powerLoraContainer = container;

    renderRows(node, container);

    // Add button
    const addBtn = document.createElement("button");
    addBtn.className = "power-lora-add";
    addBtn.textContent = "+ Add LoRA";
    addBtn.onclick = () => {
        node.loraRows.push({ lora: "", strength: 1.0, on: true });
        syncToWidget(node);
        renderRows(node, container);
        updateNodeSize(node);
    };
    container.appendChild(addBtn);

    node.addDOMWidget("power_lora_ui", "div", container);
    updateNodeSize(node);
}

function renderRows(node, container) {
    // Remove existing rows
    const existingRows = container.querySelectorAll(".power-lora-row");
    existingRows.forEach(r => r.remove());

    // Add button reference
    const addBtn = container.querySelector(".power-lora-add");

    node.loraRows.forEach((row, index) => {
        const rowEl = createRowElement(node, container, row, index);
        if (addBtn) {
            container.insertBefore(rowEl, addBtn);
        } else {
            container.appendChild(rowEl);
        }

        // Fetch trigger if lora is selected
        if (row.lora && row.lora !== "None") {
            fetchTriggerWord(node, index, row.lora);
        }
    });
}

function createRowElement(node, container, row, index) {
    const rowEl = document.createElement("div");
    rowEl.className = "power-lora-row" + (row.on ? "" : " disabled");

    // Toggle
    const toggle = document.createElement("div");
    toggle.className = "power-lora-toggle" + (row.on ? " on" : "");
    toggle.onclick = () => {
        row.on = !row.on;
        toggle.classList.toggle("on", row.on);
        rowEl.classList.toggle("disabled", !row.on);
        syncToWidget(node);
    };
    rowEl.appendChild(toggle);

    // LoRA selector
    const select = document.createElement("div");
    select.className = "power-lora-select";
    select.textContent = row.lora || "Select LoRA...";
    select.title = row.lora || "Select LoRA...";
    select.onclick = (e) => {
        showLoraDropdown(node, e, select, row, index);
    };
    rowEl.appendChild(select);

    // Strength input
    const strength = document.createElement("input");
    strength.className = "power-lora-strength";
    strength.type = "number";
    strength.step = "0.05";
    strength.value = row.strength;
    strength.onchange = (e) => {
        row.strength = parseFloat(e.target.value) || 1.0;
        syncToWidget(node);
    };
    rowEl.appendChild(strength);

    // Trigger display
    const triggerEl = document.createElement("div");
    triggerEl.className = "power-lora-trigger";
    triggerEl.id = `trigger-${index}`;
    triggerEl.textContent = node.triggerDisplays[index] || "";
    triggerEl.title = node.triggerDisplays[index] || "";
    if (!node.triggerDisplays[index]) {
        triggerEl.style.display = "none";
    }
    rowEl.appendChild(triggerEl);

    // Delete button
    const deleteBtn = document.createElement("button");
    deleteBtn.className = "power-lora-delete";
    deleteBtn.textContent = "×";
    deleteBtn.onclick = () => {
        node.loraRows.splice(index, 1);
        delete node.triggerDisplays[index];
        syncToWidget(node);
        renderRows(node, container);
        updateNodeSize(node);
    };
    rowEl.appendChild(deleteBtn);

    return rowEl;
}

function showLoraDropdown(node, event, selectEl, row, index) {
    // Remove any existing dropdown
    const existing = document.querySelector(".power-lora-dropdown");
    if (existing) existing.remove();

    const dropdown = document.createElement("div");
    dropdown.className = "power-lora-dropdown";

    // Search box
    const searchBox = document.createElement("div");
    searchBox.className = "power-lora-dropdown-search";
    const searchInput = document.createElement("input");
    searchInput.placeholder = "Search LoRAs...";
    searchBox.appendChild(searchInput);
    dropdown.appendChild(searchBox);

    // Items container
    const itemsContainer = document.createElement("div");
    dropdown.appendChild(itemsContainer);

    function renderItems(filter = "") {
        itemsContainer.innerHTML = "";
        const filterLower = filter.toLowerCase();

        // Add "None" option first
        const noneItem = document.createElement("div");
        noneItem.className = "power-lora-dropdown-item";
        noneItem.textContent = "None";
        noneItem.onclick = () => {
            row.lora = "";
            selectEl.textContent = "Select LoRA...";
            selectEl.title = "Select LoRA...";
            node.triggerDisplays[index] = "";
            const triggerEl = document.getElementById(`trigger-${index}`);
            if (triggerEl) {
                triggerEl.textContent = "";
                triggerEl.style.display = "none";
            }
            syncToWidget(node);
            dropdown.remove();
        };
        itemsContainer.appendChild(noneItem);

        // Filter and add items
        const filtered = node.loraList.filter(lora =>
            lora.toLowerCase().includes(filterLower)
        );

        filtered.slice(0, 50).forEach(lora => {
            const item = document.createElement("div");
            item.className = "power-lora-dropdown-item";
            item.textContent = lora;
            item.title = lora;
            item.onclick = () => {
                row.lora = lora;
                selectEl.textContent = lora;
                selectEl.title = lora;
                syncToWidget(node);
                fetchTriggerWord(node, index, lora);
                dropdown.remove();
            };
            itemsContainer.appendChild(item);
        });

        if (filtered.length > 50) {
            const more = document.createElement("div");
            more.className = "power-lora-dropdown-item";
            more.textContent = `... ${filtered.length - 50} more (type to filter)`;
            more.style.color = "#888";
            more.style.fontStyle = "italic";
            itemsContainer.appendChild(more);
        }
    }

    searchInput.oninput = (e) => {
        renderItems(e.target.value);
    };

    renderItems();

    document.body.appendChild(dropdown);

    // Position dropdown
    const rect = selectEl.getBoundingClientRect();
    dropdown.style.left = rect.left + "px";
    dropdown.style.top = (rect.bottom + 2) + "px";
    dropdown.style.width = Math.max(rect.width, 250) + "px";

    // Focus search
    setTimeout(() => searchInput.focus(), 10);

    // Close on click outside
    const closeHandler = (e) => {
        if (!dropdown.contains(e.target) && e.target !== selectEl) {
            dropdown.remove();
            document.removeEventListener("mousedown", closeHandler);
        }
    };
    setTimeout(() => {
        document.addEventListener("mousedown", closeHandler);
    }, 10);
}

async function fetchTriggerWord(node, index, loraName) {
    if (!loraName || loraName === "None") {
        node.triggerDisplays[index] = "";
        updateTriggerDisplay(index, "");
        return;
    }

    // Check cache
    if (triggerCache[loraName]) {
        node.triggerDisplays[index] = triggerCache[loraName];
        updateTriggerDisplay(index, triggerCache[loraName]);
        return;
    }

    try {
        const response = await api.fetchApi("/boudoir/lora-trigger", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lora_name: loraName })
        });

        if (response.ok) {
            const data = await response.json();
            if (data.trigger_word) {
                const trigger = data.trigger_word.trim();
                triggerCache[loraName] = trigger;
                node.triggerDisplays[index] = trigger;
                updateTriggerDisplay(index, trigger);
            }
        }
    } catch (error) {
        console.log("[PowerLoRA] Could not fetch trigger:", error);
    }
}

function updateTriggerDisplay(index, trigger) {
    const triggerEl = document.getElementById(`trigger-${index}`);
    if (triggerEl) {
        triggerEl.textContent = trigger;
        triggerEl.title = trigger;
        triggerEl.style.display = trigger ? "block" : "none";
    }
}

function updateNodeSize(node) {
    const rowCount = node.loraRows.length;
    const baseHeight = 100; // Model input + add button
    const rowHeight = 36;
    const newHeight = baseHeight + (rowCount * rowHeight);

    node.size[1] = Math.max(newHeight, 120);
    if (node.graph) {
        node.graph.setDirtyCanvas(true, true);
    }
}
