"""
Load Lora From Folder + Trigger - ComfyUI Custom Node
Loads LORAs from a specified subfolder with trigger word passthrough/concatenation
"""

import os
import folder_paths
from nodes import LoraLoader


def get_lora_subfolders():
    """Get list of subfolders in the loras directory"""
    lora_paths = folder_paths.get_folder_paths("loras")
    subfolders = set()

    for lora_path in lora_paths:
        if os.path.exists(lora_path):
            for item in os.listdir(lora_path):
                item_path = os.path.join(lora_path, item)
                if os.path.isdir(item_path) and not item.startswith('.'):
                    subfolders.add(item)

    # Return sorted list, with empty option first for "all loras"
    return sorted(list(subfolders))


def get_loras_in_folder(folder_name):
    """Get list of LORA files in a specific subfolder"""
    lora_paths = folder_paths.get_folder_paths("loras")
    lora_files = []
    extensions = folder_paths.folder_names_and_paths["loras"][1]

    for lora_path in lora_paths:
        target_folder = os.path.join(lora_path, folder_name)
        if os.path.exists(target_folder):
            for root, dirs, files in os.walk(target_folder):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in extensions):
                        # Get relative path from loras folder
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, lora_path)
                        lora_files.append(rel_path)

    return sorted(lora_files) if lora_files else ["None"]


def get_lora_trigger_words(lora_name):
    """
    Get trigger words for a LORA.
    Looks for a .txt file with the same name as the LORA.
    """
    lora_paths = folder_paths.get_folder_paths("loras")

    # Remove extension from lora_name
    base_name = os.path.splitext(lora_name)[0]

    for lora_path in lora_paths:
        # Check for .txt file with same name
        txt_path = os.path.join(lora_path, base_name + ".txt")
        if os.path.exists(txt_path):
            try:
                with open(txt_path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            except Exception as e:
                print(f"[LoraFolderLoader] Error reading trigger file: {e}")

    return ""


class LoadLoraFolderTrigger:
    """
    Load a LORA from a specific subfolder with trigger word support.
    Supports daisy-chaining trigger words from multiple nodes.
    """

    def __init__(self):
        self.lora_loader = LoraLoader()

    @classmethod
    def INPUT_TYPES(cls):
        subfolders = get_lora_subfolders()
        if not subfolders:
            subfolders = ["(no subfolders found)"]

        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_folder": (subfolders, {
                    "default": subfolders[0] if subfolders else "",
                    "tooltip": "Select the LORA subfolder to load from"
                }),
                "lora_name": ("STRING", {
                    "default": "",
                    "tooltip": "LORA filename (populated by folder selection)"
                }),
                "strength_model": ("FLOAT", {
                    "default": 1.0,
                    "min": -20.0,
                    "max": 20.0,
                    "step": 0.01,
                    "tooltip": "Strength for the model"
                }),
                "strength_clip": ("FLOAT", {
                    "default": 1.0,
                    "min": -20.0,
                    "max": 20.0,
                    "step": 0.01,
                    "tooltip": "Strength for CLIP"
                }),
                "use_trigger": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Include this LORA's trigger words in output"
                }),
            },
            "optional": {
                "trigger_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Incoming trigger words from previous node"
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "TRIGGER")
    FUNCTION = "load_lora"
    CATEGORY = "Boudoir Studio/Loaders"

    def load_lora(self, model, clip, lora_folder, lora_name, strength_model, strength_clip, use_trigger, trigger_in=None):
        # Handle empty or invalid lora_name
        if not lora_name or lora_name == "None" or lora_name == "":
            # No LORA selected, just pass through
            trigger_out = trigger_in if trigger_in else ""
            return (model, clip, trigger_out)

        # Load the LORA
        try:
            model, clip = self.lora_loader.load_lora(model, clip, lora_name, strength_model, strength_clip)
        except Exception as e:
            print(f"[LoadLoraFolderTrigger] Error loading LORA '{lora_name}': {e}")
            trigger_out = trigger_in if trigger_in else ""
            return (model, clip, trigger_out)

        # Build trigger output
        triggers = []

        # Add incoming triggers first
        if trigger_in and trigger_in.strip():
            triggers.append(trigger_in.strip())

        # Add this LORA's triggers if enabled
        if use_trigger:
            lora_triggers = get_lora_trigger_words(lora_name)
            if lora_triggers:
                triggers.append(lora_triggers)

        # Combine with comma separator
        trigger_out = ", ".join(triggers) if triggers else ""

        return (model, clip, trigger_out)


class LoadLoraFolderTriggerAdvanced:
    """
    Advanced version with dynamic LORA dropdown based on selected folder.
    Uses a workaround to refresh the LORA list when folder changes.
    """

    def __init__(self):
        self.lora_loader = LoraLoader()

    @classmethod
    def INPUT_TYPES(cls):
        subfolders = get_lora_subfolders()
        if not subfolders:
            subfolders = ["(no subfolders found)"]

        # Get all loras for the first folder as default
        default_loras = get_loras_in_folder(subfolders[0]) if subfolders else ["None"]

        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_folder": (subfolders, {
                    "default": subfolders[0] if subfolders else "",
                    "tooltip": "Select the LORA subfolder"
                }),
                "lora_name": (default_loras, {
                    "default": default_loras[0] if default_loras else "None",
                    "tooltip": "Select the LORA file"
                }),
                "strength_model": ("FLOAT", {
                    "default": 1.0,
                    "min": -20.0,
                    "max": 20.0,
                    "step": 0.01,
                    "tooltip": "Strength for the model"
                }),
                "strength_clip": ("FLOAT", {
                    "default": 1.0,
                    "min": -20.0,
                    "max": 20.0,
                    "step": 0.01,
                    "tooltip": "Strength for CLIP"
                }),
                "use_trigger": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Include this LORA's trigger words in output"
                }),
            },
            "optional": {
                "trigger_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Incoming trigger words from previous node"
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "TRIGGER")
    FUNCTION = "load_lora"
    CATEGORY = "Boudoir Studio/Loaders"

    def load_lora(self, model, clip, lora_folder, lora_name, strength_model, strength_clip, use_trigger, trigger_in=None):
        # Handle empty or invalid lora_name
        if not lora_name or lora_name == "None" or lora_name == "":
            trigger_out = trigger_in if trigger_in else ""
            return (model, clip, trigger_out)

        # Load the LORA
        try:
            model, clip = self.lora_loader.load_lora(model, clip, lora_name, strength_model, strength_clip)
        except Exception as e:
            print(f"[LoadLoraFolderTriggerAdvanced] Error loading LORA '{lora_name}': {e}")
            trigger_out = trigger_in if trigger_in else ""
            return (model, clip, trigger_out)

        # Build trigger output
        triggers = []

        # Add incoming triggers first
        if trigger_in and trigger_in.strip():
            triggers.append(trigger_in.strip())

        # Add this LORA's triggers if enabled
        if use_trigger:
            lora_triggers = get_lora_trigger_words(lora_name)
            if lora_triggers:
                triggers.append(lora_triggers)

        # Combine with comma separator
        trigger_out = ", ".join(triggers) if triggers else ""

        return (model, clip, trigger_out)


# Node mappings
NODE_CLASS_MAPPINGS = {
    "LoadLoraFolderTrigger": LoadLoraFolderTrigger,
    "LoadLoraFolderTriggerAdvanced": LoadLoraFolderTriggerAdvanced,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadLoraFolderTrigger": "Load Lora (Folder) + Trigger",
    "LoadLoraFolderTriggerAdvanced": "Load Lora (Folder) + Trigger [Advanced]",
}
