import { app } from "../../scripts/app.js";

// Cache for loras by folder
const loraCache = {};

async function fetchLorasInFolder(folder) {
    if (loraCache[folder]) {
        return loraCache[folder];
    }

    try {
        const response = await fetch(`/boudoir/loras-in-folder?folder=${encodeURIComponent(folder)}`);
        const data = await response.json();
        loraCache[folder] = data.loras || [];
        return loraCache[folder];
    } catch (error) {
        console.error("Error fetching loras for folder:", folder, error);
        return [];
    }
}

app.registerExtension({
    name: "Boudoir.LoRAFolderLoader",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Handle both node types
        if (nodeData.name === "LoRAFolderLoaderWithTrigger" ||
            nodeData.name === "LoRAFolderLoaderModelClipWithTrigger") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = async function() {
                if (onNodeCreated) {
                    onNodeCreated.apply(this, arguments);
                }

                const node = this;
                const folderWidget = node.widgets.find(w => w.name === "lora_folder");
                const loraWidget = node.widgets.find(w => w.name === "lora_name");

                if (!folderWidget || !loraWidget) {
                    console.log("Widgets not found", node.widgets.map(w => w.name));
                    return;
                }

                // Store original values
                const originalLoraOptions = loraWidget.options?.values || [];

                // Function to update lora dropdown based on selected folder
                async function updateLoraDropdown(folder) {
                    if (!folder || folder === "(no subfolders)") {
                        loraWidget.options.values = ["None"];
                        loraWidget.value = "None";
                        return;
                    }

                    const loras = await fetchLorasInFolder(folder);

                    if (loras.length === 0) {
                        loraWidget.options.values = ["None"];
                        loraWidget.value = "None";
                    } else {
                        loraWidget.options.values = loras;
                        // Keep current value if it's in the new list, otherwise use first
                        if (!loras.includes(loraWidget.value)) {
                            loraWidget.value = loras[0];
                        }
                    }

                    // Force widget to redraw
                    if (node.graph) {
                        node.setDirtyCanvas(true, true);
                    }
                }

                // Override the folder widget's callback
                const originalCallback = folderWidget.callback;
                folderWidget.callback = async function(value) {
                    if (originalCallback) {
                        originalCallback.call(this, value);
                    }
                    await updateLoraDropdown(value);
                };

                // Also handle when value is set directly (e.g., loading a workflow)
                const originalFolderValue = Object.getOwnPropertyDescriptor(folderWidget, 'value') ||
                    Object.getOwnPropertyDescriptor(Object.getPrototypeOf(folderWidget), 'value');

                if (originalFolderValue && originalFolderValue.set) {
                    Object.defineProperty(folderWidget, 'value', {
                        get: originalFolderValue.get,
                        set: function(v) {
                            originalFolderValue.set.call(this, v);
                            // Delay to ensure the value is set
                            setTimeout(() => updateLoraDropdown(v), 100);
                        },
                        configurable: true
                    });
                }

                // Initialize with current folder selection
                if (folderWidget.value) {
                    await updateLoraDropdown(folderWidget.value);
                }
            };

            // Handle workflow loading
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = async function(info) {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }

                const node = this;
                const folderWidget = node.widgets.find(w => w.name === "lora_folder");
                const loraWidget = node.widgets.find(w => w.name === "lora_name");

                if (folderWidget && loraWidget && info.widgets_values) {
                    // Find the folder value from saved workflow
                    const folderIndex = node.widgets.findIndex(w => w.name === "lora_folder");
                    const loraIndex = node.widgets.findIndex(w => w.name === "lora_name");

                    if (folderIndex >= 0 && info.widgets_values[folderIndex]) {
                        const savedFolder = info.widgets_values[folderIndex];
                        const savedLora = loraIndex >= 0 ? info.widgets_values[loraIndex] : null;

                        // Fetch loras for the saved folder
                        const loras = await fetchLorasInFolder(savedFolder);
                        if (loras.length > 0) {
                            loraWidget.options.values = loras;
                            // Restore saved lora if it exists in the folder
                            if (savedLora && loras.includes(savedLora)) {
                                loraWidget.value = savedLora;
                            }
                        }
                    }
                }
            };
        }
    }
});
