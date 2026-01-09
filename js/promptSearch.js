import { app } from "../../scripts/app.js";

// Use local proxy to avoid CORS issues
const API_BASE = "/boudoir";

app.registerExtension({
    name: "BoudoirPromptLibrary.SearchWidget",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "BoudoirPromptSearchWidget") {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function() {
            onNodeCreated?.apply(this, arguments);

            const node = this;

            // Find the backend widgets
            const promptWidget = node.widgets?.find(w => w.name === "selected_prompt");
            const idWidget = node.widgets?.find(w => w.name === "selected_id");
            const categoryWidget = node.widgets?.find(w => w.name === "selected_category");

            // Hide/minimize the backend widgets since we'll control them via UI
            if (promptWidget) {
                promptWidget.computeSize = () => [0, -4];
                promptWidget.type = "hidden";
            }
            if (idWidget) {
                idWidget.computeSize = () => [0, -4];
                idWidget.type = "hidden";
            }
            if (categoryWidget) {
                categoryWidget.computeSize = () => [0, -4];
                categoryWidget.type = "hidden";
            }

            // Create search input widget
            const searchWidget = this.addWidget("text", "search", "", () => {}, {
                placeholder: "Type keywords to search..."
            });

            // Create filter category dropdown
            const filterWidget = this.addWidget("combo", "filter_category", "any", () => {}, {
                values: ["any", "artistic", "elegant", "fantasy", "dramatic", "romantic", "erotic", "couples", "implied"]
            });

            // Create search button
            this.addWidget("button", "search_btn", "Search Prompts", () => {
                performSearch(node, searchWidget.value, filterWidget.value);
            });

            // Create results display (readonly text showing selection)
            const selectedWidget = this.addWidget("text", "selected_display", "(no prompt selected)", () => {}, {
                multiline: true
            });

            // Make it visually distinct
            if (selectedWidget.inputEl) {
                selectedWidget.inputEl.readOnly = true;
                selectedWidget.inputEl.style.background = "#1a1a2e";
                selectedWidget.inputEl.style.color = "#7aa2f7";
                selectedWidget.inputEl.style.minHeight = "60px";
            }

            // Store widget references
            node.searchWidget = searchWidget;
            node.filterWidget = filterWidget;
            node.selectedWidget = selectedWidget;
            node.promptWidget = promptWidget;
            node.idWidget = idWidget;
            node.categoryWidgetBackend = categoryWidget;

            // Set initial size
            node.size = [400, 200];
        };

        // Override serialization to save UI state
        const onSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function(o) {
            onSerialize?.apply(this, arguments);
            // Save the display text for restoration
            if (this.selectedWidget) {
                o.selectedDisplay = this.selectedWidget.value;
            }
        };

        // Override deserialization to restore UI state
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(o) {
            onConfigure?.apply(this, arguments);

            // Restore the display widget after a short delay (widgets need to be created)
            setTimeout(() => {
                if (o.selectedDisplay && this.selectedWidget) {
                    this.selectedWidget.value = o.selectedDisplay;
                }
                // Also update display from the actual widget values
                updateSelectedDisplayFromWidgets(this);
            }, 100);
        };
    },

    async nodeCreated(node) {
        if (node.comfyClass !== "BoudoirPromptSearchWidget") {
            return;
        }

        // After node is created, set up widget references
        setTimeout(() => {
            const promptWidget = node.widgets?.find(w => w.name === "selected_prompt");
            const idWidget = node.widgets?.find(w => w.name === "selected_id");
            const categoryWidget = node.widgets?.find(w => w.name === "selected_category");

            node.promptWidget = promptWidget;
            node.idWidget = idWidget;
            node.categoryWidgetBackend = categoryWidget;

            // Update display from restored values
            updateSelectedDisplayFromWidgets(node);
        }, 150);
    }
});

function updateSelectedDisplayFromWidgets(node) {
    if (!node.selectedWidget) return;

    const promptWidget = node.promptWidget || node.widgets?.find(w => w.name === "selected_prompt");
    const categoryWidget = node.categoryWidgetBackend || node.widgets?.find(w => w.name === "selected_category");

    if (promptWidget?.value) {
        const text = promptWidget.value;
        const category = categoryWidget?.value || "";
        const preview = text.length > 80 ? text.substring(0, 80) + "..." : text;
        node.selectedWidget.value = category ? `[${category}] ${preview}` : preview;
    } else {
        node.selectedWidget.value = "(no prompt selected)";
    }
}

async function performSearch(node, query, category) {
    if (!query.trim()) {
        showResultsDialog(node, [], "Please enter a search term");
        return;
    }

    try {
        const params = new URLSearchParams({ q: query, limit: "50" });
        if (category !== "any") {
            params.append("category", category);
        }

        const response = await fetch(`${API_BASE}/prompt-search?${params}`);
        const data = await response.json();

        if (!data.success || !data.prompts?.length) {
            showResultsDialog(node, [], "No prompts found");
            return;
        }

        showResultsDialog(node, data.prompts, `Found ${data.prompts.length} prompts`);

    } catch (error) {
        console.error("[BoudoirPromptSearch] Error:", error);
        showResultsDialog(node, [], `Error: ${error.message}`);
    }
}

function showResultsDialog(node, prompts, title) {
    // Remove existing dialog if any
    const existing = document.getElementById("boudoir-prompt-dialog");
    if (existing) existing.remove();

    // Create dialog overlay
    const overlay = document.createElement("div");
    overlay.id = "boudoir-prompt-dialog";
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    `;

    // Create dialog box
    const dialog = document.createElement("div");
    dialog.style.cssText = `
        background: #1e1e1e;
        border: 1px solid #444;
        border-radius: 8px;
        width: 700px;
        max-height: 80vh;
        display: flex;
        flex-direction: column;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    `;

    // Header
    const header = document.createElement("div");
    header.style.cssText = `
        padding: 12px 16px;
        border-bottom: 1px solid #444;
        display: flex;
        justify-content: space-between;
        align-items: center;
        background: #252525;
        border-radius: 8px 8px 0 0;
    `;
    header.innerHTML = `
        <span style="color: #fff; font-weight: 600; font-size: 14px;">${title}</span>
        <button id="boudoir-close-btn" style="background: none; border: none; color: #888; font-size: 24px; cursor: pointer; line-height: 1; padding: 0 4px;">&times;</button>
    `;

    // Results container
    const resultsContainer = document.createElement("div");
    resultsContainer.style.cssText = `
        flex: 1;
        overflow-y: auto;
        padding: 8px;
        max-height: 60vh;
    `;

    if (prompts.length === 0) {
        resultsContainer.innerHTML = `<div style="color: #888; text-align: center; padding: 40px; font-size: 14px;">No results found</div>`;
    } else {
        prompts.forEach((prompt) => {
            const item = document.createElement("div");
            item.style.cssText = `
                padding: 14px;
                margin: 6px 0;
                background: #2a2a2a;
                border: 1px solid #383838;
                border-radius: 6px;
                cursor: pointer;
                transition: all 0.15s ease;
            `;
            item.onmouseenter = () => {
                item.style.background = "#353535";
                item.style.borderColor = "#7aa2f7";
            };
            item.onmouseleave = () => {
                item.style.background = "#2a2a2a";
                item.style.borderColor = "#383838";
            };

            const preview = prompt.text.length > 200 ? prompt.text.substring(0, 200) + "..." : prompt.text;

            item.innerHTML = `
                <div style="display: flex; justify-content: space-between; margin-bottom: 8px; align-items: center;">
                    <span style="color: #7aa2f7; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; background: #2d3a50; padding: 3px 8px; border-radius: 3px;">${prompt.category}</span>
                    <span style="color: #666; font-size: 11px;">ID: ${prompt.id} &nbsp;|&nbsp; Used: ${prompt.use_count || 0}x</span>
                </div>
                <div style="color: #ccc; font-size: 13px; line-height: 1.5;">${preview}</div>
            `;

            item.onclick = () => selectPrompt(node, prompt, overlay);
            resultsContainer.appendChild(item);
        });
    }

    dialog.appendChild(header);
    dialog.appendChild(resultsContainer);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    // Close handlers
    document.getElementById("boudoir-close-btn").onclick = () => overlay.remove();
    overlay.onclick = (e) => {
        if (e.target === overlay) overlay.remove();
    };

    // ESC key to close
    const escHandler = (e) => {
        if (e.key === "Escape") {
            overlay.remove();
            document.removeEventListener("keydown", escHandler);
        }
    };
    document.addEventListener("keydown", escHandler);
}

function selectPrompt(node, prompt, overlay) {
    // Find the backend widgets
    const promptWidget = node.promptWidget || node.widgets?.find(w => w.name === "selected_prompt");
    const idWidget = node.idWidget || node.widgets?.find(w => w.name === "selected_id");
    const categoryWidget = node.categoryWidgetBackend || node.widgets?.find(w => w.name === "selected_category");

    // Update the actual widget values (this is what gets sent to the backend)
    if (promptWidget) {
        promptWidget.value = prompt.text;
    }
    if (idWidget) {
        idWidget.value = prompt.id;
    }
    if (categoryWidget) {
        categoryWidget.value = prompt.category;
    }

    // Update the display widget
    if (node.selectedWidget) {
        const preview = prompt.text.length > 80 ? prompt.text.substring(0, 80) + "..." : prompt.text;
        node.selectedWidget.value = `[${prompt.category}] ${preview}`;
    }

    // Close dialog
    overlay.remove();

    // Mark node as needing update
    node.setDirtyCanvas(true, true);

    console.log("[BoudoirPromptSearch] Selected prompt:", prompt.id, prompt.category);
    console.log("[BoudoirPromptSearch] Widget values set - prompt:", promptWidget?.value?.substring(0, 50) + "...");
}
