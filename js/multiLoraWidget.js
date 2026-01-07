import { app } from "../../scripts/app.js";
import { api } from "../../../scripts/api.js";

// Cache for trigger words
const triggerCache = {};

app.registerExtension({
    name: "BoudoirPromptLibrary.MultiLoRAWidget",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "MultiLoRALoaderWithTriggers") {
            return;
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function() {
            onNodeCreated?.apply(this, arguments);

            const node = this;
            node.triggerDisplays = {};

            // Setup after widgets are created
            setTimeout(() => {
                setupTriggerDisplays(node);
            }, 100);
        };

        // Hook into configure to restore state
        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function(info) {
            onConfigure?.apply(this, arguments);
            setTimeout(() => {
                setupTriggerDisplays(this);
                // Fetch triggers for any pre-selected loras
                for (const widget of this.widgets || []) {
                    if (widget.name.startsWith("lora_") && widget.value && widget.value !== "None") {
                        fetchTriggerWord(this, widget.name, widget.value);
                    }
                }
            }, 200);
        };
    },

    nodeCreated(node) {
        if (node.comfyClass !== "MultiLoRALoaderWithTriggers") {
            return;
        }

        setTimeout(() => {
            setupTriggerDisplays(node);

            // Hook into widget callbacks
            for (const widget of node.widgets || []) {
                if (widget.name.startsWith("lora_") && widget.type === "combo") {
                    const originalCallback = widget.callback;
                    widget.callback = function(value) {
                        if (originalCallback) originalCallback.call(this, value);
                        fetchTriggerWord(node, widget.name, value);
                    };

                    // Initial fetch
                    if (widget.value && widget.value !== "None") {
                        fetchTriggerWord(node, widget.name, widget.value);
                    }
                }
            }
        }, 200);
    }
});

function setupTriggerDisplays(node) {
    if (!node.widgets) return;

    // Initialize trigger displays for each lora slot
    for (let i = 1; i <= 5; i++) {
        if (!node.triggerDisplays[i]) {
            node.triggerDisplays[i] = "";
        }
    }

    // Override draw to show triggers
    const originalOnDrawForeground = node.onDrawForeground;
    node.onDrawForeground = function(ctx) {
        if (originalOnDrawForeground) {
            originalOnDrawForeground.apply(this, arguments);
        }
        drawTriggers(this, ctx);
    };
}

function drawTriggers(node, ctx) {
    if (!node.widgets || !node.triggerDisplays) return;

    ctx.save();
    ctx.font = "bold 11px Arial";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";

    for (const widget of node.widgets) {
        if (widget.name.startsWith("lora_") && widget.type === "combo") {
            const num = widget.name.split("_")[1];
            const trigger = node.triggerDisplays[num];

            if (trigger && widget.last_y !== undefined) {
                const y = widget.last_y + 10;
                const x = node.size[0] - 15;

                // Draw background pill
                const text = trigger.trim();
                if (text) {
                    const metrics = ctx.measureText(text);
                    const padding = 6;
                    const pillWidth = metrics.width + padding * 2;
                    const pillHeight = 16;

                    ctx.fillStyle = "rgba(122, 162, 247, 0.2)";
                    ctx.beginPath();
                    ctx.roundRect(x - pillWidth, y - pillHeight/2, pillWidth, pillHeight, 4);
                    ctx.fill();

                    // Draw text
                    ctx.fillStyle = "#7aa2f7";
                    ctx.fillText(text, x - padding, y);
                }
            }
        }
    }

    ctx.restore();
}

async function fetchTriggerWord(node, widgetName, loraName) {
    const num = widgetName.split("_")[1];

    if (!loraName || loraName === "None") {
        node.triggerDisplays[num] = "";
        node.setDirtyCanvas(true, true);
        return;
    }

    // Check cache
    if (triggerCache[loraName]) {
        node.triggerDisplays[num] = triggerCache[loraName];
        node.setDirtyCanvas(true, true);
        return;
    }

    // Use ComfyUI's internal API to get trigger word
    // We'll call a custom endpoint on our node
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
                node.triggerDisplays[num] = trigger;
            }
        }
    } catch (error) {
        console.log("[MultiLoRA] Could not fetch trigger:", error);
    }

    node.setDirtyCanvas(true, true);
}
