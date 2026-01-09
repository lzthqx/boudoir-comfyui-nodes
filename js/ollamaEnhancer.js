import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// Extension to handle text display for Ollama Prompt Enhancer nodes
app.registerExtension({
    name: "BoudoirPromptLibrary.OllamaEnhancer",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Handle OllamaPromptEnhancer, OllamaPromptEnhancerAdvanced, and BoudoirSuperNode
        const enhancerNodes = ["OllamaPromptEnhancer", "OllamaPromptEnhancerAdvanced", "BoudoirSuperNode"];
        if (!enhancerNodes.includes(nodeData.name)) {
            return;
        }

        // Store the original onExecuted function
        const onExecuted = nodeType.prototype.onExecuted;

        nodeType.prototype.onExecuted = function(message) {
            onExecuted?.apply(this, arguments);

            // Get the text from the UI message
            if (message?.text) {
                const text = Array.isArray(message.text) ? message.text[0] : message.text;

                // Find the display widget
                const displayWidget = this.widgets?.find(w => w.name === "enhanced_display");

                if (displayWidget) {
                    displayWidget.value = text;

                    // Also update the DOM element if it exists
                    if (displayWidget.inputEl) {
                        displayWidget.inputEl.value = text;
                    }

                    this.setDirtyCanvas(true, true);
                }
            }
        };

        // Hook into node creation to add display widget
        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function() {
            onNodeCreated?.apply(this, arguments);

            const node = this;

            // Add display widget after a short delay to ensure other widgets are created
            setTimeout(() => {
                // Check if display widget already exists
                if (node.widgets?.find(w => w.name === "enhanced_display")) {
                    return;
                }

                // Use ComfyWidgets to create a proper STRING widget with multiline
                const widget = ComfyWidgets["STRING"](node, "enhanced_display", ["STRING", {
                    multiline: true,
                    default: "(run workflow to see enhanced prompt)"
                }], app);

                const displayWidget = widget.widget;

                // Style the widget to look like a display output
                if (displayWidget.inputEl) {
                    displayWidget.inputEl.readOnly = true;
                    displayWidget.inputEl.style.backgroundColor = "#1a1a2e";
                    displayWidget.inputEl.style.color = "#7aa2f7";
                    displayWidget.inputEl.style.border = "1px solid #3d3d5c";
                    displayWidget.inputEl.style.borderRadius = "4px";
                    displayWidget.inputEl.style.height = "120px";
                    displayWidget.inputEl.style.minHeight = "120px";
                    displayWidget.inputEl.style.fontFamily = "monospace";
                    displayWidget.inputEl.style.fontSize = "11px";
                    displayWidget.inputEl.style.padding = "8px";
                    displayWidget.inputEl.style.resize = "vertical";
                    displayWidget.inputEl.style.lineHeight = "1.4";
                    displayWidget.inputEl.style.cursor = "default";
                }

                // Store reference
                node.enhancedDisplayWidget = displayWidget;

                // Resize node to fit the new widget
                const targetHeight = node.computeSize()[1];
                if (node.size[1] < targetHeight) {
                    node.setSize([Math.max(node.size[0], 380), targetHeight]);
                }

            }, 100);
        };

        // Serialize the display value
        const onSerialize = nodeType.prototype.onSerialize;
        nodeType.prototype.onSerialize = function(o) {
            onSerialize?.apply(this, arguments);
            const displayWidget = this.widgets?.find(w => w.name === "enhanced_display");
            if (displayWidget) {
                o.enhancedDisplayValue = displayWidget.value;
            }
        };

        // Restore the display value on load
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(o) {
            onConfigure?.apply(this, arguments);
            const node = this;

            setTimeout(() => {
                if (o.enhancedDisplayValue) {
                    const displayWidget = node.widgets?.find(w => w.name === "enhanced_display");
                    if (displayWidget) {
                        displayWidget.value = o.enhancedDisplayValue;
                        if (displayWidget.inputEl) {
                            displayWidget.inputEl.value = o.enhancedDisplayValue;
                        }
                        node.setDirtyCanvas(true, true);
                    }
                }
            }, 200);
        };
    }
});
