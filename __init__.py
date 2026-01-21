"""
Boudoir Studio Prompt Library - ComfyUI Custom Nodes
Fetch prompts from the BoudoirStudioAdmin prompt database
"""

import urllib.request
import urllib.parse
import json
import random
import os

# Default API base URL - uses host IP for Docker network access
API_BASE_URL = "http://10.10.10.138:3001/api/prompts"

# Timer storage for execution timing
_execution_timers = {}
_workflow_start_time = None
_last_prompt_id = None

def format_duration(seconds):
    """Format seconds as human-readable duration (e.g., '1m30s', '45s')"""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if secs == 0:
        return f"{minutes}m"
    return f"{minutes}m{secs}s"


# Set web directory for frontend JS extension
WEB_DIRECTORY = "./js"

# Cache for categories (refreshed on each ComfyUI restart)
_cached_categories = None

def get_prompt_categories():
    """Fetch prompt categories from the API (cached for session)"""
    global _cached_categories
    if _cached_categories is not None:
        return _cached_categories

    try:
        url = f"{API_BASE_URL}/categories"
        req = urllib.request.Request(url, headers={'User-Agent': 'ComfyUI-BoudoirPromptLibrary'})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("success") and data.get("categories"):
                _cached_categories = ["any"] + sorted(data["categories"])
                return _cached_categories
    except Exception as e:
        print(f"[BoudoirPromptLibrary] Could not fetch categories: {e}")

    # Fallback to default categories if API fails
    _cached_categories = ["any", "artistic", "dramatic", "elegant", "erotic", "fantasy", "fashion", "fine art", "modern", "nature", "other", "romantic", "vintage"]
    return _cached_categories

# Register custom API routes
from aiohttp import web
from server import PromptServer
import aiohttp

# Proxy endpoint for prompt search (avoids CORS issues)
@PromptServer.instance.routes.get("/boudoir/prompt-search")
async def proxy_prompt_search(request):
    """Proxy search requests to the prompt API to avoid CORS"""
    try:
        query = request.query.get("q", "")
        category = request.query.get("category", "")
        limit = request.query.get("limit", "50")

        params = {"q": query, "limit": limit}
        if category and category != "any":
            params["category"] = category

        url = f"{API_BASE_URL}/search?{urllib.parse.urlencode(params)}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "prompts": []})


@PromptServer.instance.routes.get("/boudoir/prompt-random")
async def proxy_prompt_random(request):
    """Proxy random prompt requests to the prompt API"""
    try:
        category = request.query.get("category", "")

        url = f"{API_BASE_URL}/random"
        if category and category != "any":
            url += f"?category={urllib.parse.quote(category)}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "prompt": None})


@PromptServer.instance.routes.get("/boudoir/prompt-categories")
async def proxy_prompt_categories(request):
    """Proxy categories request to the prompt API"""
    try:
        url = f"{API_BASE_URL}/categories"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                data = await resp.json()
                return web.json_response(data)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e), "categories": []})

@PromptServer.instance.routes.get("/boudoir/lora-folders")
async def get_lora_folders(request):
    """Get list of all LoRA folders and subfolders (recursive)"""
    try:
        import folder_paths
        lora_paths = folder_paths.get_folder_paths("loras")
        all_folders = set()

        for lora_path in lora_paths:
            if os.path.exists(lora_path):
                for root, dirs, files in os.walk(lora_path):
                    # Filter out hidden directories
                    dirs[:] = [d for d in dirs if not d.startswith('.')]

                    # Get relative path from lora root
                    rel_path = os.path.relpath(root, lora_path)
                    if rel_path != '.':
                        all_folders.add(rel_path)

                    # Also add immediate subdirectories
                    for d in dirs:
                        sub_path = os.path.join(rel_path, d) if rel_path != '.' else d
                        all_folders.add(sub_path)

        return web.json_response({"folders": sorted(list(all_folders))})
    except Exception as e:
        return web.json_response({"error": str(e), "folders": []})


@PromptServer.instance.routes.get("/boudoir/loras-in-folder")
async def get_loras_in_folder_api(request):
    """Get list of LoRA files directly in a specific folder (not recursive)"""
    try:
        import folder_paths
        folder_name = request.query.get("folder", "")

        if not folder_name:
            return web.json_response({"error": "No folder specified", "loras": []})

        lora_paths = folder_paths.get_folder_paths("loras")
        lora_files = []
        extensions = {'.safetensors', '.ckpt', '.pt', '.bin', '.pth'}

        for lora_path in lora_paths:
            target_folder = os.path.join(lora_path, folder_name)
            if os.path.exists(target_folder):
                # Only get files directly in this folder, not subfolders
                for file in os.listdir(target_folder):
                    file_path = os.path.join(target_folder, file)
                    if os.path.isfile(file_path) and any(file.lower().endswith(ext) for ext in extensions):
                        rel_path = os.path.relpath(file_path, lora_path)
                        lora_files.append(rel_path)

        return web.json_response({"loras": sorted(lora_files)})
    except Exception as e:
        return web.json_response({"error": str(e), "loras": []})


@PromptServer.instance.routes.post("/boudoir/lora-trigger")
async def get_lora_trigger(request):
    """Extract trigger word from a LoRA file"""
    try:
        data = await request.json()
        lora_name = data.get("lora_name", "")

        if not lora_name:
            return web.json_response({"error": "No lora_name provided"})

        import folder_paths
        from safetensors import safe_open

        lora_path = folder_paths.get_full_path("loras", lora_name)
        if not lora_path or not os.path.exists(lora_path):
            return web.json_response({"error": "LoRA not found", "trigger_word": ""})

        with safe_open(lora_path, framework='pt') as f:
            meta = f.metadata()

        if not meta:
            return web.json_response({"trigger_word": "", "message": "No metadata"})

        trigger_word = meta.get('modelspec.trigger_phrase', '')

        # Try tag frequency
        if not trigger_word and 'ss_tag_frequency' in meta:
            try:
                tags_data = json.loads(meta['ss_tag_frequency'])
                all_tags = {}
                for dataset, tag_dict in tags_data.items():
                    for tag, count in tag_dict.items():
                        tag_clean = tag.strip()
                        if tag_clean:
                            all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                if all_tags:
                    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                    trigger_word = sorted_tags[0][0]
            except:
                pass

        # Fallback to output name
        if not trigger_word:
            trigger_word = meta.get('ss_output_name', '')

        return web.json_response({"trigger_word": trigger_word})

    except Exception as e:
        return web.json_response({"error": str(e), "trigger_word": ""})


class BoudoirPromptSearch:
    """
    Search the Boudoir Studio prompt database by keyword.
    Returns a list of matching prompts that can be selected from.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "search_query": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "Search keywords..."
                }),
                "category": (get_prompt_categories(), {
                    "default": "any"
                }),
                "result_index": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 99,
                    "step": 1,
                    "display": "number"
                }),
            },
            "optional": {
                "api_url": ("STRING", {
                    "default": API_BASE_URL,
                    "multiline": False
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompt_text", "category", "prompt_id")
    FUNCTION = "search_prompts"
    CATEGORY = "Boudoir Studio/Prompts"

    def search_prompts(self, search_query, category, result_index, api_url=API_BASE_URL):
        if not search_query.strip():
            return ("", "", 0)

        try:
            # Build URL with query params
            params = {"q": search_query, "limit": 100}
            if category != "any":
                params["category"] = category

            url = f"{api_url}/search?{urllib.parse.urlencode(params)}"

            req = urllib.request.Request(url)
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            if not data.get("success") or not data.get("prompts"):
                return ("No prompts found", "", 0)

            prompts = data["prompts"]

            # Clamp index to available results
            index = min(result_index, len(prompts) - 1)
            selected = prompts[index]

            return (
                selected.get("text", ""),
                selected.get("category", ""),
                selected.get("id", 0)
            )

        except Exception as e:
            print(f"[BoudoirPromptSearch] Error: {e}")
            return (f"Error: {str(e)}", "", 0)


class BoudoirRandomPrompt:
    """
    Get a random prompt from the Boudoir Studio prompt database.
    Optionally filter by category.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "category": (get_prompt_categories(), {
                    "default": "any"
                }),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "step": 1,
                    "display": "number"
                }),
            },
            "optional": {
                "trigger": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "forceInput": True,
                    "placeholder": "Trigger word(s) to prepend"
                }),
                "api_url": ("STRING", {
                    "default": API_BASE_URL,
                    "multiline": False
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompt_text", "category", "prompt_id")
    FUNCTION = "get_random_prompt"
    CATEGORY = "Boudoir Studio/Prompts"

    @classmethod
    def IS_CHANGED(cls, category, seed, trigger="", api_url=API_BASE_URL):
        # Force re-execution when seed changes
        return seed

    def get_random_prompt(self, category, seed, trigger="", api_url=API_BASE_URL):
        try:
            # Build URL
            url = f"{api_url}/random"
            if category != "any":
                url += f"?category={urllib.parse.quote(category)}"

            req = urllib.request.Request(url)
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            if not data.get("success") or not data.get("prompt"):
                return ("No prompts available", "", 0)

            prompt = data["prompt"]
            prompt_text = prompt.get("text", "")

            # Prepend trigger word(s) if provided
            if trigger and trigger.strip():
                # Ensure proper spacing: " trigger " + " " + "prompt"
                trigger_clean = trigger.strip()
                prompt_text = f"{trigger_clean} {prompt_text}"

            return (
                prompt_text,
                prompt.get("category", ""),
                prompt.get("id", 0)
            )

        except Exception as e:
            print(f"[BoudoirRandomPrompt] Error: {e}")
            return (f"Error: {str(e)}", "", 0)


class BoudoirPromptById:
    """
    Fetch a specific prompt by its ID from the Boudoir Studio database.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt_id": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 999999,
                    "step": 1,
                    "display": "number"
                }),
            },
            "optional": {
                "api_url": ("STRING", {
                    "default": API_BASE_URL,
                    "multiline": False
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt_text", "category")
    FUNCTION = "get_prompt_by_id"
    CATEGORY = "Boudoir Studio/Prompts"

    def get_prompt_by_id(self, prompt_id, api_url=API_BASE_URL):
        try:
            url = f"{api_url}/{prompt_id}"

            req = urllib.request.Request(url)
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            if not data.get("success") or not data.get("prompt"):
                return ("Prompt not found", "")

            prompt = data["prompt"]

            return (
                prompt.get("text", ""),
                prompt.get("category", "")
            )

        except Exception as e:
            print(f"[BoudoirPromptById] Error: {e}")
            return (f"Error: {str(e)}", "")


class BoudoirPromptCategories:
    """
    Get all available prompt categories from the database.
    Outputs a comma-separated list of categories.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "api_url": ("STRING", {
                    "default": API_BASE_URL,
                    "multiline": False
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("categories",)
    FUNCTION = "get_categories"
    CATEGORY = "Boudoir Studio/Prompts"

    def get_categories(self, api_url=API_BASE_URL):
        try:
            url = f"{api_url}/categories"

            req = urllib.request.Request(url)
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            if not data.get("success") or not data.get("categories"):
                return ("",)

            return (", ".join(data["categories"]),)

        except Exception as e:
            print(f"[BoudoirPromptCategories] Error: {e}")
            return (f"Error: {str(e)}",)


class BoudoirPromptSearchWidget:
    """
    Interactive search widget with popup dialog to browse and select prompts.
    Select a prompt before running the workflow.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selected_prompt": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "Click 'Search Prompts' to select a prompt"
                }),
                "selected_id": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 999999,
                }),
                "selected_category": ("STRING", {
                    "default": "",
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("prompt_text", "category", "prompt_id")
    FUNCTION = "get_selected_prompt"
    CATEGORY = "Boudoir Studio/Prompts"

    def get_selected_prompt(self, selected_prompt="", selected_id=0, selected_category=""):
        # The JS widget stores the selection in these widgets
        if not selected_prompt:
            return ("No prompt selected - use Search button", "", 0)
        return (selected_prompt, selected_category, selected_id)


class LoRATriggerWordExtractor:
    """
    Extract trigger words from a LoRA file's metadata.
    Reads the safetensors metadata to find training tags and trigger phrases.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lora_name": ("STRING", {
                    "default": "",
                    "multiline": False,
                    "placeholder": "path/to/lora.safetensors"
                }),
            },
            "optional": {
                "num_tags": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "display": "number"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("trigger_word", "top_tags", "output_name")
    FUNCTION = "extract_trigger"
    CATEGORY = "Boudoir Studio/LoRA"

    def extract_trigger(self, lora_name, num_tags=1):
        try:
            from safetensors import safe_open
            import folder_paths

            # Find the lora file
            lora_path = None

            # Check if it's an absolute path
            if os.path.isabs(lora_name) and os.path.exists(lora_name):
                lora_path = lora_name
            else:
                # Search in ComfyUI's lora folders
                lora_dirs = folder_paths.get_folder_paths("loras")
                for lora_dir in lora_dirs:
                    potential_path = os.path.join(lora_dir, lora_name)
                    if os.path.exists(potential_path):
                        lora_path = potential_path
                        break
                    # Also try with .safetensors extension
                    if not lora_name.endswith('.safetensors'):
                        potential_path = os.path.join(lora_dir, lora_name + '.safetensors')
                        if os.path.exists(potential_path):
                            lora_path = potential_path
                            break

            if not lora_path:
                return (f"LoRA not found: {lora_name}", "", "")

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ("No metadata in LoRA", "", "")

            # Get output name (often the trigger word itself)
            output_name = meta.get('ss_output_name', '')

            # Check for explicit trigger phrase (CivitAI style)
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            # Get top training tags
            top_tags_list = []
            if 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    # Sort by frequency
                    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                    top_tags_list = [tag for tag, count in sorted_tags[:num_tags]]

                    # If no explicit trigger, use the most frequent tag
                    if not trigger_word and top_tags_list:
                        trigger_word = top_tags_list[0]
                except json.JSONDecodeError:
                    pass

            # Fallback to output_name if still no trigger
            if not trigger_word and output_name:
                trigger_word = output_name

            top_tags = ", ".join(top_tags_list) if top_tags_list else ""

            # Add padding spaces so trigger word doesn't merge with adjacent text
            if trigger_word:
                trigger_word = f" {trigger_word} "

            return (trigger_word, top_tags, output_name)

        except ImportError:
            return ("safetensors library not available", "", "")
        except Exception as e:
            print(f"[LoRATriggerWordExtractor] Error: {e}")
            return (f"Error: {str(e)}", "", "")


class LoRATriggerWordFromLoader:
    """
    Extract trigger words from a LoRA that's already loaded via LoraLoader.
    Connect to the lora_name output of a LoRA Stacker or use the name directly.
    """

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        lora_list = folder_paths.get_filename_list("loras")
        return {
            "required": {
                "lora_name": (lora_list, ),
            },
            "optional": {
                "num_tags": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "display": "number"
                }),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "STRING")
    RETURN_NAMES = ("trigger_word", "top_tags", "output_name")
    FUNCTION = "extract_trigger"
    CATEGORY = "Boudoir Studio/LoRA"

    def extract_trigger(self, lora_name, num_tags=1):
        try:
            from safetensors import safe_open
            import folder_paths

            # Get the full path from ComfyUI's folder system
            lora_path = folder_paths.get_full_path("loras", lora_name)

            if not lora_path or not os.path.exists(lora_path):
                return (f"LoRA not found: {lora_name}", "", "")

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ("No metadata in LoRA", "", "")

            # Get output name (often the trigger word itself)
            output_name = meta.get('ss_output_name', '')

            # Check for explicit trigger phrase
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            # Get top training tags
            top_tags_list = []
            if 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                    top_tags_list = [tag for tag, count in sorted_tags[:num_tags]]

                    if not trigger_word and top_tags_list:
                        trigger_word = top_tags_list[0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word and output_name:
                trigger_word = output_name

            top_tags = ", ".join(top_tags_list) if top_tags_list else ""

            # Add padding spaces so trigger word doesn't merge with adjacent text
            if trigger_word:
                trigger_word = f" {trigger_word} "

            return (trigger_word, top_tags, output_name)

        except ImportError:
            return ("safetensors library not available", "", "")
        except Exception as e:
            print(f"[LoRATriggerWordFromLoader] Error: {e}")
            return (f"Error: {str(e)}", "", "")


class LoRALoaderWithTrigger:
    """
    Combined LoRA loader that also extracts and outputs the trigger word.
    Loads the LoRA onto the model and provides the trigger word for your prompt.
    """

    def __init__(self):
        self.loaded_lora = None

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        return {
            "required": {
                "model": ("MODEL",),
                "lora_name": (folder_paths.get_filename_list("loras"), ),
                "strength_model": ("FLOAT", {
                    "default": 1.0,
                    "min": -100.0,
                    "max": 100.0,
                    "step": 0.01
                }),
            },
            "optional": {
                "num_tags": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "display": "number"
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "trigger_word", "top_tags")
    FUNCTION = "load_lora_with_trigger"
    CATEGORY = "Boudoir Studio/LoRA"

    def load_lora_with_trigger(self, model, lora_name, strength_model, num_tags=1):
        import folder_paths
        import comfy.utils
        import comfy.sd

        # Load the LoRA
        if strength_model == 0:
            model_lora = model
        else:
            lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
            lora = None

            if self.loaded_lora is not None:
                if self.loaded_lora[0] == lora_path:
                    lora = self.loaded_lora[1]
                else:
                    self.loaded_lora = None

            if lora is None:
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                self.loaded_lora = (lora_path, lora)

            model_lora, _ = comfy.sd.load_lora_for_models(model, None, lora, strength_model, 0)

        # Extract trigger word
        trigger_word, top_tags = self._extract_trigger(lora_name, num_tags)

        return (model_lora, trigger_word, top_tags)

    def _extract_trigger(self, lora_name, num_tags):
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ("", "")

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ("", "")

            output_name = meta.get('ss_output_name', '')
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            top_tags_list = []
            if 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                    top_tags_list = [tag for tag, count in sorted_tags[:num_tags]]

                    if not trigger_word and top_tags_list:
                        trigger_word = top_tags_list[0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word and output_name:
                trigger_word = output_name

            top_tags = ", ".join(top_tags_list) if top_tags_list else ""

            # Add padding spaces so trigger word doesn't merge with adjacent text
            if trigger_word:
                trigger_word = f" {trigger_word} "

            return (trigger_word, top_tags)

        except Exception as e:
            print(f"[LoRALoaderWithTrigger] Trigger extraction error: {e}")
            return ("", "")


class LoRALoaderModelClipWithTrigger:
    """
    Combined LoRA loader (Model + CLIP) that also extracts and outputs the trigger word.
    Loads the LoRA onto both model and CLIP, and provides the trigger word for your prompt.
    """

    def __init__(self):
        self.loaded_lora = None

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_name": (folder_paths.get_filename_list("loras"), ),
                "strength_model": ("FLOAT", {
                    "default": 1.0,
                    "min": -100.0,
                    "max": 100.0,
                    "step": 0.01
                }),
                "strength_clip": ("FLOAT", {
                    "default": 1.0,
                    "min": -100.0,
                    "max": 100.0,
                    "step": 0.01
                }),
            },
            "optional": {
                "num_tags": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 20,
                    "step": 1,
                    "display": "number"
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "trigger_word", "top_tags")
    FUNCTION = "load_lora_with_trigger"
    CATEGORY = "Boudoir Studio/LoRA"

    def load_lora_with_trigger(self, model, clip, lora_name, strength_model, strength_clip, num_tags=1):
        import folder_paths
        import comfy.utils
        import comfy.sd

        # Load the LoRA
        if strength_model == 0 and strength_clip == 0:
            model_lora, clip_lora = model, clip
        else:
            lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
            lora = None

            if self.loaded_lora is not None:
                if self.loaded_lora[0] == lora_path:
                    lora = self.loaded_lora[1]
                else:
                    self.loaded_lora = None

            if lora is None:
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                self.loaded_lora = (lora_path, lora)

            model_lora, clip_lora = comfy.sd.load_lora_for_models(model, clip, lora, strength_model, strength_clip)

        # Extract trigger word
        trigger_word, top_tags = self._extract_trigger(lora_name, num_tags)

        return (model_lora, clip_lora, trigger_word, top_tags)

    def _extract_trigger(self, lora_name, num_tags):
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ("", "")

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ("", "")

            output_name = meta.get('ss_output_name', '')
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            top_tags_list = []
            if 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                    top_tags_list = [tag for tag, count in sorted_tags[:num_tags]]

                    if not trigger_word and top_tags_list:
                        trigger_word = top_tags_list[0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word and output_name:
                trigger_word = output_name

            top_tags = ", ".join(top_tags_list) if top_tags_list else ""

            # Add padding spaces so trigger word doesn't merge with adjacent text
            if trigger_word:
                trigger_word = f" {trigger_word} "

            return (trigger_word, top_tags)

        except Exception as e:
            print(f"[LoRALoaderModelClipWithTrigger] Trigger extraction error: {e}")
            return ("", "")


class MultiLoRALoaderWithTriggers:
    """
    Load up to 5 LoRAs with automatic trigger word extraction.
    Trigger words are displayed next to each LoRA and combined into a single output.
    """

    def __init__(self):
        self.loaded_loras = {}

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        lora_list = ["None"] + folder_paths.get_filename_list("loras")
        return {
            "required": {
                "model": ("MODEL",),
                "lora_1": (lora_list, ),
                "strength_1": ("FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0, "step": 0.01}),
                "lora_2": (lora_list, ),
                "strength_2": ("FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0, "step": 0.01}),
                "lora_3": (lora_list, ),
                "strength_3": ("FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0, "step": 0.01}),
                "lora_4": (lora_list, ),
                "strength_4": ("FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0, "step": 0.01}),
                "lora_5": (lora_list, ),
                "strength_5": ("FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("MODEL", "STRING")
    RETURN_NAMES = ("MODEL", "triggers")
    FUNCTION = "load_loras"
    CATEGORY = "Boudoir Studio/LoRA"

    def load_loras(self, model, lora_1, strength_1, lora_2, strength_2, lora_3, strength_3, lora_4, strength_4, lora_5, strength_5):
        import folder_paths
        import comfy.utils
        import comfy.sd

        loras = [
            (lora_1, strength_1),
            (lora_2, strength_2),
            (lora_3, strength_3),
            (lora_4, strength_4),
            (lora_5, strength_5),
        ]

        model_lora = model
        triggers = []

        for lora_name, strength in loras:
            if lora_name == "None" or strength == 0:
                continue

            # Load the LoRA
            lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
            lora = None

            if lora_path in self.loaded_loras:
                lora = self.loaded_loras[lora_path]
            else:
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                self.loaded_loras[lora_path] = lora

            model_lora, _ = comfy.sd.load_lora_for_models(model_lora, None, lora, strength, 0)

            # Extract trigger word
            trigger = self._extract_trigger(lora_name)
            if trigger.strip():
                triggers.append(trigger.strip())

        # Combine triggers with commas, space at beginning and end
        all_triggers = ", ".join(triggers)
        if all_triggers:
            all_triggers = f" {all_triggers} "

        return (model_lora, all_triggers)

    def _extract_trigger(self, lora_name):
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ""

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ""

            output_name = meta.get('ss_output_name', '')
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            if not trigger_word and 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    if all_tags:
                        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                        trigger_word = sorted_tags[0][0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word and output_name:
                trigger_word = output_name

            return trigger_word

        except Exception as e:
            print(f"[MultiLoRALoaderWithTriggers] Trigger extraction error for {lora_name}: {e}")
            return ""


class PowerLoRALoaderWithTriggers:
    """
    Dynamic LoRA loader with automatic trigger word extraction.
    Add as many LoRAs as you need with the '+ Add LoRA' button.
    Each LoRA has an on/off toggle to quickly enable/disable.
    """

    def __init__(self):
        self.loaded_loras = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
            },
            "optional": {
                "lora_data": ("STRING", {"default": "[]", "multiline": False}),
            },
        }

    RETURN_TYPES = ("MODEL", "STRING")
    RETURN_NAMES = ("MODEL", "triggers")
    FUNCTION = "load_loras"
    CATEGORY = "Boudoir Studio/LoRA"

    def load_loras(self, model, lora_data="[]", **kwargs):
        import folder_paths
        import comfy.utils
        import comfy.sd

        model_lora = model
        triggers = []

        # Parse lora_data JSON string from the UI
        # Format: [{"lora": "name.safetensors", "strength": 1.0, "on": true}, ...]
        if not lora_data or lora_data == "[]":
            return (model_lora, "")

        try:
            loras = json.loads(lora_data)
        except json.JSONDecodeError:
            print(f"[PowerLoRALoaderWithTriggers] Invalid lora_data JSON: {lora_data}")
            return (model_lora, "")

        for lora_entry in loras:
            lora_name = lora_entry.get("lora", "")
            strength = lora_entry.get("strength", 1.0)
            on = lora_entry.get("on", True)

            if not on or not lora_name or lora_name == "None" or strength == 0:
                continue

            try:
                # Load the LoRA
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = None

                if lora_path in self.loaded_loras:
                    lora = self.loaded_loras[lora_path]
                else:
                    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                    self.loaded_loras[lora_path] = lora

                model_lora, _ = comfy.sd.load_lora_for_models(model_lora, None, lora, strength, 0)

                # Extract trigger word
                trigger = self._extract_trigger(lora_name)
                if trigger.strip():
                    triggers.append(trigger.strip())

            except Exception as e:
                print(f"[PowerLoRALoaderWithTriggers] Error loading LoRA '{lora_name}': {e}")
                continue

        # Combine triggers with commas, space at beginning and end
        all_triggers = ", ".join(triggers)
        if all_triggers:
            all_triggers = f" {all_triggers} "

        return (model_lora, all_triggers)

    def _extract_trigger(self, lora_name):
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ""

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ""

            output_name = meta.get('ss_output_name', '')
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            if not trigger_word and 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    if all_tags:
                        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                        trigger_word = sorted_tags[0][0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word and output_name:
                trigger_word = output_name

            return trigger_word

        except Exception as e:
            print(f"[PowerLoRALoaderWithTriggers] Trigger extraction error for {lora_name}: {e}")
            return ""


def get_lora_subfolders():
    """Get list of all folders and subfolders in the loras directory (recursive)"""
    import folder_paths
    lora_paths = folder_paths.get_folder_paths("loras")
    all_folders = set()

    for lora_path in lora_paths:
        if os.path.exists(lora_path):
            for root, dirs, files in os.walk(lora_path):
                # Filter out hidden directories
                dirs[:] = [d for d in dirs if not d.startswith('.')]

                # Get relative path from lora root
                rel_path = os.path.relpath(root, lora_path)
                if rel_path != '.':
                    all_folders.add(rel_path)

                # Also add immediate subdirectories
                for d in dirs:
                    sub_path = os.path.join(rel_path, d) if rel_path != '.' else d
                    all_folders.add(sub_path)

    return sorted(list(all_folders)) if all_folders else ["(no subfolders)"]


def get_loras_in_folder(folder_name):
    """Get list of LORA files directly in a specific folder (not recursive)"""
    import folder_paths
    lora_paths = folder_paths.get_folder_paths("loras")
    lora_files = []
    extensions = {'.safetensors', '.ckpt', '.pt', '.bin', '.pth'}

    for lora_path in lora_paths:
        target_folder = os.path.join(lora_path, folder_name)
        if os.path.exists(target_folder):
            # Only get files directly in this folder, not subfolders
            for file in os.listdir(target_folder):
                file_path = os.path.join(target_folder, file)
                if os.path.isfile(file_path) and any(file.lower().endswith(ext) for ext in extensions):
                    rel_path = os.path.relpath(file_path, lora_path)
                    lora_files.append(rel_path)

    return sorted(lora_files) if lora_files else ["None"]


class LoRAFolderLoaderWithTrigger:
    """
    Load a LoRA from a specific subfolder with trigger word chaining support.
    Select a folder, then select a LoRA from that folder.
    Supports daisy-chaining: connect TRIGGER output to next node's trigger_in.
    """

    def __init__(self):
        self.loaded_lora = None

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        subfolders = get_lora_subfolders()
        # Get loras from first folder as default list
        default_loras = get_loras_in_folder(subfolders[0]) if subfolders[0] != "(no subfolders)" else ["None"]

        return {
            "required": {
                "model": ("MODEL",),
                "lora_folder": (subfolders, {
                    "tooltip": "Select the LoRA subfolder"
                }),
                "lora_name": (folder_paths.get_filename_list("loras"), {
                    "tooltip": "Select the LoRA file"
                }),
                "strength_model": ("FLOAT", {
                    "default": 1.0,
                    "min": -100.0,
                    "max": 100.0,
                    "step": 0.01,
                    "tooltip": "LoRA strength for the model"
                }),
                "use_trigger": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Include this LoRA's trigger words in output"
                }),
            },
            "optional": {
                "trigger_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Incoming trigger words from previous node in chain"
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "STRING")
    RETURN_NAMES = ("MODEL", "TRIGGER")
    FUNCTION = "load_lora"
    CATEGORY = "Boudoir Studio/LoRA"

    def load_lora(self, model, lora_folder, lora_name, strength_model, use_trigger, trigger_in=None):
        import folder_paths
        import comfy.utils
        import comfy.sd

        # Build trigger output - start with incoming triggers
        triggers = []
        if trigger_in and trigger_in.strip():
            triggers.append(trigger_in.strip())

        # Handle empty or invalid lora_name
        if not lora_name or lora_name == "None":
            trigger_out = ", ".join(triggers) if triggers else ""
            return (model, trigger_out)

        # Load the LoRA
        model_lora = model
        if strength_model != 0:
            try:
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = None

                if self.loaded_lora is not None:
                    if self.loaded_lora[0] == lora_path:
                        lora = self.loaded_lora[1]
                    else:
                        self.loaded_lora = None

                if lora is None:
                    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                    self.loaded_lora = (lora_path, lora)

                model_lora, _ = comfy.sd.load_lora_for_models(model, None, lora, strength_model, 0)

                # Extract trigger word if enabled
                if use_trigger:
                    trigger_word = self._extract_trigger(lora_name)
                    if trigger_word.strip():
                        triggers.append(trigger_word.strip())

            except Exception as e:
                print(f"[LoRAFolderLoaderWithTrigger] Error loading LoRA '{lora_name}': {e}")

        trigger_out = ", ".join(triggers) if triggers else ""
        return (model_lora, trigger_out)

    def _extract_trigger(self, lora_name):
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ""

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ""

            # Check for explicit trigger phrase
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            # Try tag frequency
            if not trigger_word and 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    if all_tags:
                        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                        trigger_word = sorted_tags[0][0]
                except json.JSONDecodeError:
                    pass

            # Fallback to output name
            if not trigger_word:
                trigger_word = meta.get('ss_output_name', '')

            return trigger_word

        except Exception as e:
            print(f"[LoRAFolderLoaderWithTrigger] Trigger extraction error: {e}")
            return ""


class LoRAFolderLoaderModelClipWithTrigger:
    """
    Load a LoRA (Model+CLIP) from a specific subfolder with trigger word chaining.
    Select a folder, then select a LoRA from that folder.
    Supports daisy-chaining: connect TRIGGER output to next node's trigger_in.
    """

    def __init__(self):
        self.loaded_lora = None

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        subfolders = get_lora_subfolders()

        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "lora_folder": (subfolders, {
                    "tooltip": "Select the LoRA subfolder"
                }),
                "lora_name": (folder_paths.get_filename_list("loras"), {
                    "tooltip": "Select the LoRA file"
                }),
                "strength_model": ("FLOAT", {
                    "default": 1.0,
                    "min": -100.0,
                    "max": 100.0,
                    "step": 0.01,
                    "tooltip": "LoRA strength for the model"
                }),
                "strength_clip": ("FLOAT", {
                    "default": 1.0,
                    "min": -100.0,
                    "max": 100.0,
                    "step": 0.01,
                    "tooltip": "LoRA strength for CLIP"
                }),
                "use_trigger": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "Include this LoRA's trigger words in output"
                }),
            },
            "optional": {
                "trigger_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Incoming trigger words from previous node in chain"
                }),
            }
        }

    RETURN_TYPES = ("MODEL", "CLIP", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "TRIGGER")
    FUNCTION = "load_lora"
    CATEGORY = "Boudoir Studio/LoRA"

    def load_lora(self, model, clip, lora_folder, lora_name, strength_model, strength_clip, use_trigger, trigger_in=None):
        import folder_paths
        import comfy.utils
        import comfy.sd

        # Build trigger output - start with incoming triggers
        triggers = []
        if trigger_in and trigger_in.strip():
            triggers.append(trigger_in.strip())

        # Handle empty or invalid lora_name
        if not lora_name or lora_name == "None":
            trigger_out = ", ".join(triggers) if triggers else ""
            return (model, clip, trigger_out)

        # Load the LoRA
        model_lora, clip_lora = model, clip
        if strength_model != 0 or strength_clip != 0:
            try:
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
                lora = None

                if self.loaded_lora is not None:
                    if self.loaded_lora[0] == lora_path:
                        lora = self.loaded_lora[1]
                    else:
                        self.loaded_lora = None

                if lora is None:
                    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                    self.loaded_lora = (lora_path, lora)

                model_lora, clip_lora = comfy.sd.load_lora_for_models(model, clip, lora, strength_model, strength_clip)

                # Extract trigger word if enabled
                if use_trigger:
                    trigger_word = self._extract_trigger(lora_name)
                    if trigger_word.strip():
                        triggers.append(trigger_word.strip())

            except Exception as e:
                print(f"[LoRAFolderLoaderModelClipWithTrigger] Error loading LoRA '{lora_name}': {e}")

        trigger_out = ", ".join(triggers) if triggers else ""
        return (model_lora, clip_lora, trigger_out)

    def _extract_trigger(self, lora_name):
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ""

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ""

            trigger_word = meta.get('modelspec.trigger_phrase', '')

            if not trigger_word and 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    if all_tags:
                        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                        trigger_word = sorted_tags[0][0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word:
                trigger_word = meta.get('ss_output_name', '')

            return trigger_word

        except Exception as e:
            print(f"[LoRAFolderLoaderModelClipWithTrigger] Trigger extraction error: {e}")
            return ""


def get_available_gpus():
    """Get list of available GPU devices for selection"""
    import torch
    devices = ["auto"]  # Let ComfyUI decide
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            name = torch.cuda.get_device_name(i)
            devices.append(f"cuda:{i} ({name})")
    return devices


class BoudoirAllInOneNode:
    """
    All-in-one node for Boudoir Studio workflows.
    Combines CLIP/VAE loading, LoRA with triggers, resolution selection,
    and prompt handling (manual or random from Boudoir API).

    Supports optional CLIP and VAE inputs from checkpoint loaders.
    If CLIP/VAE inputs are connected, they take priority over the built-in selectors.
    """

    RESOLUTIONS = [
        "1:1 - 1328x1328 (Square)",
        "16:9 - 1664x928 (Landscape)",
        "9:16 - 928x1664 (Portrait)",
        "4:3 - 1472x1104 (Landscape)",
        "3:4 - 1104x1472 (Portrait)",
        "3:2 - 1584x1056 (Landscape)",
        "2:3 - 1056x1584 (Portrait)",
    ]

    def __init__(self):
        self.loaded_lora = None

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        gpu_options = get_available_gpus()
        return {
            "required": {
                "model": ("MODEL",),
                "clip_name": (["None"] + folder_paths.get_filename_list("clip"), {"tooltip": "Select CLIP model to load (ignored if CLIP input is connected)"}),
                "clip_device": (gpu_options, {"default": "auto", "tooltip": "GPU for CLIP model (only used with built-in loader)"}),
                "vae_name": (["None"] + folder_paths.get_filename_list("vae"), {"tooltip": "Select VAE to load (ignored if VAE input is connected)"}),
                "vae_device": (gpu_options, {"default": "auto", "tooltip": "GPU for VAE model (only used with built-in loader)"}),
                "resolution": (cls.RESOLUTIONS, {"default": "1:1 - 1328x1328 (Square)"}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 64, "step": 1}),
                "use_random_prompt": ("BOOLEAN", {"default": False, "label_on": "Random Prompt", "label_off": "Manual Prompt"}),
                "prompt_category": (get_prompt_categories(), {"default": "any"}),
                "positive_prompt": ("STRING", {"default": "", "multiline": True, "placeholder": "Positive prompt (used when Manual Prompt is selected)"}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True, "placeholder": "Negative prompt"}),
                "lora_name": (["None"] + folder_paths.get_filename_list("loras"), {"tooltip": "Select LoRA (optional)"}),
                "lora_strength_model": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "lora_strength_clip": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "use_trigger": ("BOOLEAN", {"default": True, "label_on": "Add Trigger Word", "label_off": "No Trigger"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "step": 1, "tooltip": "Seed for random prompt selection"}),
            },
            "optional": {
                "clip_in": ("CLIP", {"tooltip": "Optional CLIP input from checkpoint loader (takes priority over built-in selector)"}),
                "vae_in": ("VAE", {"tooltip": "Optional VAE input from checkpoint loader (takes priority over built-in selector)"}),
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "LATENT", "CONDITIONING", "CONDITIONING", "VAE", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "LATENT", "POSITIVE", "NEGATIVE", "VAE", "prompt_text", "trigger_words", "prompt_id")
    FUNCTION = "process"
    CATEGORY = "Boudoir Studio"

    @classmethod
    def IS_CHANGED(cls, use_random_prompt, seed, **kwargs):
        if use_random_prompt:
            return seed
        return ""

    def process(self, model, clip_name, clip_device, vae_name, vae_device, resolution, batch_size,
                use_random_prompt, prompt_category, positive_prompt, negative_prompt,
                lora_name, lora_strength_model, lora_strength_clip, use_trigger, seed,
                clip_in=None, vae_in=None):
        import torch
        import folder_paths
        import comfy.utils
        import comfy.sd
        import comfy.model_management

        # Parse device selection (extract "cuda:0" from "cuda:0 (GPU Name)")
        def parse_device(device_str):
            if device_str == "auto" or not device_str:
                return None  # Let ComfyUI decide
            return device_str.split(" ")[0]  # Get "cuda:0" from "cuda:0 (Name)"

        clip_dev = parse_device(clip_device)
        vae_dev = parse_device(vae_device)

        # === CLIP: Use input if connected, otherwise load from selector ===
        clip = None
        if clip_in is not None:
            # Use the connected CLIP input (from checkpoint loader)
            clip = clip_in
        elif clip_name and clip_name != "None":
            # Fall back to built-in CLIP loader
            clip_path = folder_paths.get_full_path_or_raise("clip", clip_name)
            model_options = {}
            if clip_dev:
                model_options["load_device"] = torch.device(clip_dev)
            clip = comfy.sd.load_clip(ckpt_paths=[clip_path],
                                       embedding_directory=folder_paths.get_folder_paths("embeddings"),
                                       model_options=model_options)

        # === VAE: Use input if connected, otherwise load from selector ===
        vae = None
        if vae_in is not None:
            # Use the connected VAE input (from checkpoint loader)
            vae = vae_in
        elif vae_name and vae_name != "None":
            # Fall back to built-in VAE loader
            vae_path = folder_paths.get_full_path_or_raise("vae", vae_name)
            vae_sd = comfy.utils.load_torch_file(vae_path)
            if vae_dev:
                vae = comfy.sd.VAE(sd=vae_sd, device=torch.device(vae_dev))
            else:
                vae = comfy.sd.VAE(sd=vae_sd)

        # === Apply LoRA and extract trigger ===
        model_lora = model
        clip_lora = clip
        trigger_words = ""

        if lora_name and lora_name != "None":
            lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)
            lora = None

            if self.loaded_lora is not None:
                if self.loaded_lora[0] == lora_path:
                    lora = self.loaded_lora[1]
                else:
                    self.loaded_lora = None

            if lora is None:
                lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                self.loaded_lora = (lora_path, lora)

            if lora_strength_model != 0 or lora_strength_clip != 0:
                model_lora, clip_lora = comfy.sd.load_lora_for_models(
                    model, clip, lora, lora_strength_model, lora_strength_clip
                )

            # Extract trigger word if enabled
            if use_trigger:
                trigger_words = self._extract_trigger(lora_name)

        # === Get prompt (random or manual) ===
        prompt_id = ""
        if use_random_prompt:
            final_prompt, prompt_id = self._get_random_prompt(prompt_category)
        else:
            final_prompt = positive_prompt

        # Prepend trigger words to prompt
        if trigger_words.strip():
            final_prompt = f"{trigger_words.strip()} {final_prompt}"

        # === Create latent ===
        dimensions = resolution.split(" - ")[1].split(" ")[0]
        width, height = map(int, dimensions.split("x"))
        latent = torch.zeros([batch_size, 4, height // 8, width // 8])

        # === Encode prompts (only if CLIP is loaded) ===
        positive_cond = None
        negative_cond = None
        if clip_lora is not None:
            tokens_pos = clip_lora.tokenize(final_prompt)
            cond_pos, pooled_pos = clip_lora.encode_from_tokens(tokens_pos, return_pooled=True)
            positive_cond = [[cond_pos, {"pooled_output": pooled_pos}]]

            tokens_neg = clip_lora.tokenize(negative_prompt)
            cond_neg, pooled_neg = clip_lora.encode_from_tokens(tokens_neg, return_pooled=True)
            negative_cond = [[cond_neg, {"pooled_output": pooled_neg}]]

        return (model_lora, clip_lora, {"samples": latent}, positive_cond, negative_cond, vae, final_prompt, trigger_words, prompt_id)

    def _extract_trigger(self, lora_name):
        """Extract trigger word from LoRA metadata"""
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ""

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ""

            # Check for explicit trigger phrase
            trigger_word = meta.get('modelspec.trigger_phrase', '')

            # Try tag frequency
            if not trigger_word and 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    if all_tags:
                        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                        trigger_word = sorted_tags[0][0]
                except json.JSONDecodeError:
                    pass

            # Fallback to output name
            if not trigger_word:
                trigger_word = meta.get('ss_output_name', '')

            return trigger_word

        except Exception as e:
            print(f"[BoudoirAllInOneNode] Trigger extraction error: {e}")
            return ""

    def _get_random_prompt(self, category):
        """Fetch random prompt from Boudoir API. Returns (prompt_text, prompt_id)"""
        try:
            url = f"{API_BASE_URL}/random"
            if category != "any":
                url += f"?category={urllib.parse.quote(category)}"

            req = urllib.request.Request(url)
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            if data.get("success") and data.get("prompt"):
                prompt_text = data["prompt"].get("text", "")
                prompt_id = str(data["prompt"].get("id", ""))
                return (prompt_text, prompt_id)

            return ("", "")

        except Exception as e:
            print(f"[BoudoirAllInOneNode] Random prompt error: {e}")
            return ("", "")


class BoudoirSaveImageWithText:
    """
    Save image and accompanying text file with matching filenames.
    Text file is saved immediately after image with the same name.
    """

    def __init__(self):
        self.output_dir = None
        self.type = "output"
        self.prefix_append = ""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "filename_prefix": ("STRING", {"default": "image"}),
                "image_format": (["png", "jpg", "webp"], {"default": "png"}),
                "quality": ("INT", {"default": 95, "min": 1, "max": 100, "step": 1, "tooltip": "Quality for JPG/WebP (ignored for PNG)"}),
                "preview_only": ("BOOLEAN", {"default": False, "label_on": "Preview Only", "label_off": "Save Image"}),
                "save_text": ("BOOLEAN", {"default": True, "label_on": "Save Text", "label_off": "No Text"}),
                "text_extension": ([".txt", ".csv", ".json", ".md"], {"default": ".txt"}),
                "append_generation_time": ("BOOLEAN", {"default": False, "label_on": "Append Time", "label_off": "No Time", "tooltip": "Append generation time (e.g., _1m30s) to filename"}),
            },
            "optional": {
                "text_content": ("STRING", {"forceInput": True, "multiline": True}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("image_path", "text_path")
    OUTPUT_NODE = True
    FUNCTION = "save_image_and_text"
    CATEGORY = "Boudoir Studio"

    def save_image_and_text(self, images, filename_prefix, image_format, quality, preview_only, save_text, text_extension=".txt", append_generation_time=False, text_content="", prompt=None, extra_pnginfo=None):
        import folder_paths
        from PIL import Image
        import numpy as np

        output_dir = folder_paths.get_output_directory()
        temp_dir = folder_paths.get_temp_directory()

        results = []
        saved_image_path = ""
        saved_text_path = ""

        for idx, image in enumerate(images):
            # Convert tensor to PIL Image
            i = 255. * image.cpu().numpy()
            img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

            # Generate unique filename with counter
            file_prefix = filename_prefix.strip()

            # Calculate and append generation time if enabled
            time_suffix = ""
            if append_generation_time:
                global _workflow_start_time
                import time as time_module
                if _workflow_start_time is not None:
                    elapsed = time_module.time() - _workflow_start_time
                    time_suffix = f"_{format_duration(elapsed)}"
                    print(f"[BoudoirSaveImageWithText] Generation time: {format_duration(elapsed)}")
                else:
                    print(f"[BoudoirSaveImageWithText] WARNING: No workflow start time recorded")
            
            # Append time suffix to prefix
            file_prefix = file_prefix + time_suffix

            if preview_only:
                # For preview, save to temp directory
                save_dir = temp_dir
                file_type = "temp"
                # Simple temp filename
                import time
                filename_base = f"{file_prefix}_preview_{int(time.time()*1000)}"
            else:
                # For saving, use output directory with counter
                save_dir = output_dir
                file_type = "output"

                # Find the next available counter
                counter = 1
                while True:
                    if len(images) > 1:
                        filename_base = f"{file_prefix}_{counter:05d}_{idx+1:02d}"
                    else:
                        filename_base = f"{file_prefix}_{counter:05d}_"

                    image_filename = f"{filename_base}.{image_format}"
                    image_path = os.path.join(save_dir, image_filename)

                    if not os.path.exists(image_path):
                        break
                    counter += 1

            image_filename = f"{filename_base}.{image_format}"
            image_path = os.path.join(save_dir, image_filename)

            # Save image
            if image_format == "png":
                # Add metadata for PNG
                metadata = None
                if extra_pnginfo is not None and not preview_only:
                    from PIL import PngImagePlugin
                    metadata = PngImagePlugin.PngInfo()
                    for k, v in extra_pnginfo.items():
                        metadata.add_text(k, json.dumps(v))
                # Add enhanced prompt as custom field (for extraction tools)
                if text_content and not preview_only:
                    if metadata is None:
                        from PIL import PngImagePlugin
                        metadata = PngImagePlugin.PngInfo()
                    metadata.add_text("enhanced_display", text_content)
                img.save(image_path, pnginfo=metadata, compress_level=4)
            elif image_format == "jpg":
                img.save(image_path, quality=quality)
            else:  # webp
                img.save(image_path, quality=quality)

            saved_image_path = image_path
            if preview_only:
                print(f"[BoudoirSaveImageWithText] Preview: {image_path}")
            else:
                print(f"[BoudoirSaveImageWithText] Saved image: {image_path}")

            # Save text file with same base name (only if not preview_only and save_text is enabled)
            if not preview_only and save_text and text_content:
                text_filename = f"{filename_base}{text_extension}"
                text_path = os.path.join(save_dir, text_filename)

                try:
                    with open(text_path, 'w', encoding='utf-8') as f:
                        f.write(text_content)
                    saved_text_path = text_path
                    print(f"[BoudoirSaveImageWithText] Saved text: {text_path}")
                except Exception as e:
                    print(f"[BoudoirSaveImageWithText] Error saving text: {e}")

            results.append({
                "filename": image_filename,
                "subfolder": "",
                "type": file_type
            })

        return {"ui": {"images": results}, "result": (saved_image_path, saved_text_path)}


class BoudoirSaveText:
    """
    Save text content to a file with configurable extension and output location.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text_content": ("STRING", {"forceInput": True, "multiline": True}),
                "filename": ("STRING", {"forceInput": True, "default": "output"}),
                "extension": ([".txt", ".csv", ".json", ".md"], {"default": ".txt"}),
                "output_location": (["default_output", "custom"], {"default": "default_output"}),
                "custom_folder": ("STRING", {"default": "", "placeholder": "Custom folder path (if 'custom' selected)"}),
                "match_image_counter": ("BOOLEAN", {"default": True, "label_on": "Match Image Name", "label_off": "Use Filename Input"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("saved_filepath",)
    OUTPUT_NODE = True
    FUNCTION = "save_text"
    CATEGORY = "Boudoir Studio"

    def save_text(self, text_content, filename, extension, output_location, custom_folder, match_image_counter):
        import folder_paths
        import glob

        # Determine output folder
        if output_location == "default_output":
            output_folder = folder_paths.get_output_directory()
        else:
            output_folder = custom_folder.strip()
            if not output_folder:
                output_folder = folder_paths.get_output_directory()

        # Ensure folder exists
        os.makedirs(output_folder, exist_ok=True)

        # Clean base filename (remove any existing extension)
        base_filename = filename.strip()
        for ext in [".txt", ".csv", ".json", ".md", ".png", ".jpg", ".jpeg", ".webp"]:
            if base_filename.lower().endswith(ext):
                base_filename = base_filename[:-len(ext)]

        if match_image_counter:
            # Find the most recently modified image that starts with this base filename
            image_extensions = ["*.png", "*.jpg", "*.jpeg", "*.webp"]
            matching_images = []

            for img_ext in image_extensions:
                pattern = os.path.join(output_folder, f"{base_filename}*{img_ext[1:]}")
                matching_images.extend(glob.glob(pattern))

            if matching_images:
                # Sort by modification time, get the most recent
                most_recent = max(matching_images, key=os.path.getmtime)
                # Use the same name (without extension)
                clean_filename = os.path.splitext(os.path.basename(most_recent))[0]
                filepath = os.path.join(output_folder, f"{clean_filename}{extension}")
            else:
                # No matching image found, use base filename
                filepath = os.path.join(output_folder, f"{base_filename}{extension}")
        else:
            # Just use the filename as-is
            filepath = os.path.join(output_folder, f"{base_filename}{extension}")

        # Write the file
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text_content)
            print(f"[BoudoirSaveText] Saved: {filepath}")
        except Exception as e:
            print(f"[BoudoirSaveText] Error saving file: {e}")
            return (f"Error: {str(e)}",)

        return (filepath,)


class BoudoirLatentResolutionSelector:
    """
    Resolution selector with preset aspect ratios for Empty Latent Image.
    Outputs a LATENT compatible with KSampler nodes.
    """

    RESOLUTIONS = [
        "1:1 - 1328x1328 (Square)",
        "16:9 - 1664x928 (Landscape)",
        "9:16 - 928x1664 (Portrait)",
        "4:3 - 1472x1104 (Landscape)",
        "3:4 - 1104x1472 (Portrait)",
        "3:2 - 1584x1056 (Landscape)",
        "2:3 - 1056x1584 (Portrait)",
    ]

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "resolution": (cls.RESOLUTIONS, {
                    "default": "1:1 - 1328x1328 (Square)"
                }),
                "batch_size": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 64,
                    "step": 1
                }),
            },
        }

    RETURN_TYPES = ("LATENT",)
    RETURN_NAMES = ("LATENT",)
    FUNCTION = "generate_latent"
    CATEGORY = "Boudoir Studio/Utils"

    def generate_latent(self, resolution, batch_size=1):
        import torch

        # Parse resolution string "1:1 - 1328x1328 (Square)" -> (1328, 1328)
        dimensions = resolution.split(" - ")[1].split(" ")[0]  # "1328x1328"
        width, height = map(int, dimensions.split("x"))

        # Create empty latent (SD1.x/SDXL style - 4 channels, 8x downscale)
        latent = torch.zeros([batch_size, 4, height // 8, width // 8])

        return ({"samples": latent},)


class ZImageResolutionSelector:
    """
    Resolution selector for Z-Image Turbo with preset resolutions.
    Outputs width, height, and an EmptySD3LatentImage compatible latent.
    """

    # All resolutions divisible by 16, optimized for Z-Image Turbo (up to 2048x2048)
    RESOLUTIONS = [
        # Square
        "1024 x 1024 (Square 1:1)",
        "1536 x 1536 (Square 1:1 Large)",
        "2048 x 2048 (Square 1:1 Max)",
        # Portrait
        "832 x 1216 (Portrait 2:3)",
        "864 x 1152 (Portrait 3:4)",
        "896 x 1152 (Portrait 3:4)",
        "768 x 1344 (Portrait 4:7)",
        "896 x 1344 (Portrait 2:3)",
        "1024 x 1536 (Portrait 2:3)",
        "1088 x 1920 (Portrait 9:16)",
        "1152 x 2048 (Portrait 9:16 Large)",
        # Landscape
        "1216 x 832 (Landscape 3:2)",
        "1152 x 864 (Landscape 4:3)",
        "1152 x 896 (Landscape 4:3)",
        "1344 x 768 (Landscape 7:4)",
        "1344 x 896 (Landscape 3:2)",
        "1536 x 1024 (Landscape 3:2)",
        "1920 x 1088 (Landscape 16:9)",
        "2048 x 1152 (Landscape 16:9 Large)",
    ]

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "resolution": (cls.RESOLUTIONS, {
                    "default": "1024 x 1024 (Square 1:1)"
                }),
            },
            "hidden": {
                "batch_size": ("INT", {"default": 1}),
            },
        }

    RETURN_TYPES = ("LATENT", "INT", "INT")
    RETURN_NAMES = ("latent", "width", "height")
    FUNCTION = "get_resolution"
    CATEGORY = "Boudoir Studio/Utils"

    def get_resolution(self, resolution, batch_size=1):
        import torch

        # Parse resolution string "1024 x 1024 (Square 1:1)" -> (1024, 1024)
        parts = resolution.split(" x ")
        width = int(parts[0])
        height = int(parts[1].split(" ")[0])

        # Create empty latent (SD3/Flux style - 16x downscale)
        latent = torch.zeros([batch_size, 16, height // 8, width // 8])

        return ({"samples": latent}, width, height)


# ============================================================================
# Ollama Prompt Enhancement Node
# ============================================================================

# Default Ollama server URL
OLLAMA_DEFAULT_URL = "http://10.10.10.138:11434"

# Default system prompt for prompt enhancement
OLLAMA_DEFAULT_SYSTEM_PROMPT = """You are a cinematic prompt enhancer for boudoir and fine art photography AI generation.

Your task is to enhance the given prompt with technical and artistic qualities WITHOUT adding new subjects, objects, props, or scene elements.

ENHANCE WITH:
- Cinematic lighting (Rembrandt, rim light, soft diffused, chiaroscuro, golden hour glow)
- Camera perspective (low angle, eye level, three-quarter view, intimate close-up)
- Depth of field (shallow DoF, creamy bokeh, sharp focus on subject)
- Mood and atmosphere (intimate, sensual, ethereal, dramatic, serene)
- Film/photo quality (35mm film grain, medium format clarity, editorial quality)
- Artistic style references (fine art, classical painting influence, contemporary)

DO NOT ADD:
- Props, furniture, fabrics, or objects not mentioned
- Background elements or locations not specified
- Clothing, accessories, or items not in the original
- Additional people or body parts

RULES:
- Preserve ALL original elements exactly as described
- Only enhance the artistic and technical presentation
- Output a single flowing prompt paragraph
- No explanations, no markdown, no commentary
- Keep output concise (50-100 words)"""

# System prompt for Super-Node - focused on pure enhancement without additions
SUPERNODE_SYSTEM_PROMPT = """You are a cinematic prompt enhancer for AI image generation.

Your task is to make the given prompt MORE DESCRIPTIVE without changing what it describes.

ENHANCE WITH:
- More specific lighting details (color temperature, direction, quality)
- Atmospheric qualities (mood, feeling, ambiance)
- Technical photography terms (depth, focus, perspective)
- Artistic descriptors (texture, tone, style)

DO NOT:
- Add new subjects, objects, or people
- Add props, furniture, or items not mentioned
- Change the core meaning or subject
- Add locations or backgrounds not specified

RULES:
- Preserve ALL original elements exactly
- Only expand and enrich existing descriptions
- Output a single flowing prompt paragraph
- No explanations, no markdown, no commentary
- Keep output concise (50-100 words)"""

def get_ollama_models(server_url=None):
    """Fetch available models from Ollama server"""
    url = server_url or OLLAMA_DEFAULT_URL
    try:
        req = urllib.request.Request(f"{url}/api/tags")
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get("models"):
                return [m["name"] for m in data["models"]]
    except Exception as e:
        print(f"[OllamaPromptEnhancer] Error fetching models: {e}")
    return ["llama3.1:latest", "mistral:latest", "qwen2.5:latest"]  # Fallback defaults


class OllamaPromptEnhancer:
    """
    Ollama-powered prompt enhancement node.
    Takes an input prompt and enhances it using a local Ollama model.
    Supports passthrough of trigger words for workflow integration.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        models = get_ollama_models()
        return {
            "required": {
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter prompt to enhance..."
                }),
                "ollama_model": (models, {
                    "default": models[0] if models else "qwen2.5:latest",
                    "tooltip": "Select Ollama model for prompt enhancement"
                }),
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": OLLAMA_DEFAULT_SYSTEM_PROMPT,
                    "tooltip": "System prompt that controls how enhancement works"
                }),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Enhance",
                    "label_off": "Bypass",
                    "tooltip": "Enable/disable enhancement (bypass passes prompt through unchanged)"
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1,
                    "tooltip": "Generation temperature (higher = more creative)"
                }),
                "prepend_trigger": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Prepend Trigger",
                    "label_off": "Append Trigger",
                    "tooltip": "Whether to prepend or append trigger words to output"
                }),
            },
            "optional": {
                "trigger_in": ("STRING", {
                    "forceInput": True,
                    "tooltip": "Trigger words to include in output prompt"
                }),
                "ollama_url": ("STRING", {
                    "default": OLLAMA_DEFAULT_URL,
                    "tooltip": "Ollama server URL (default: http://10.10.10.138:11434)"
                }),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("enhanced_prompt", "trigger_out")
    OUTPUT_NODE = True
    FUNCTION = "enhance_prompt"
    CATEGORY = "Boudoir Studio/Prompts"

    def enhance_prompt(self, prompt, ollama_model, system_prompt, enabled, temperature,
                       prepend_trigger, trigger_in=None, ollama_url=None):

        # Passthrough trigger
        trigger_out = trigger_in.strip() if trigger_in else ""

        # If disabled, just pass through with trigger handling
        if not enabled or not prompt.strip():
            final_prompt = prompt.strip()
            if trigger_out:
                if prepend_trigger:
                    final_prompt = f"{trigger_out} {final_prompt}" if final_prompt else trigger_out
                else:
                    final_prompt = f"{final_prompt} {trigger_out}" if final_prompt else trigger_out
            return {"ui": {"text": [final_prompt]}, "result": (final_prompt, trigger_out)}

        # Enhance the prompt via Ollama
        server_url = ollama_url or OLLAMA_DEFAULT_URL

        try:
            print(f"[OllamaPromptEnhancer] Enhancing prompt with {ollama_model}...")

            request_data = {
                "model": ollama_model,
                "prompt": prompt.strip(),
                "system": system_prompt,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "top_p": 0.9
                }
            }

            req = urllib.request.Request(
                f"{server_url}/api/generate",
                data=json.dumps(request_data).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                data = json.loads(response.read().decode())
                enhanced = data.get("response", "").strip()

            if not enhanced:
                print("[OllamaPromptEnhancer] Empty response, using original prompt")
                enhanced = prompt.strip()
            else:
                print(f"[OllamaPromptEnhancer] Enhanced ({len(prompt)} -> {len(enhanced)} chars)")

        except Exception as e:
            print(f"[OllamaPromptEnhancer] Error: {e}")
            enhanced = prompt.strip()  # Fall back to original on error

        # Combine with trigger words
        final_prompt = enhanced
        if trigger_out:
            if prepend_trigger:
                final_prompt = f"{trigger_out} {enhanced}"
            else:
                final_prompt = f"{enhanced} {trigger_out}"

        return {"ui": {"text": [final_prompt]}, "result": (final_prompt, trigger_out)}


class OllamaPromptEnhancerAdvanced:
    """
    Advanced Ollama prompt enhancement with CONDITIONING output.
    Encodes the enhanced prompt directly to CONDITIONING for use with samplers.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        models = get_ollama_models()
        return {
            "required": {
                "clip": ("CLIP",),
                "prompt": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Enter prompt to enhance..."
                }),
                "ollama_model": (models, {
                    "default": models[0] if models else "qwen2.5:latest",
                    "tooltip": "Select Ollama model for prompt enhancement"
                }),
                "system_prompt": ("STRING", {
                    "multiline": True,
                    "default": OLLAMA_DEFAULT_SYSTEM_PROMPT
                }),
                "enabled": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Enhance",
                    "label_off": "Bypass"
                }),
                "temperature": ("FLOAT", {
                    "default": 0.7,
                    "min": 0.0,
                    "max": 2.0,
                    "step": 0.1
                }),
                "prepend_trigger": ("BOOLEAN", {
                    "default": True,
                    "label_on": "Prepend Trigger",
                    "label_off": "Append Trigger"
                }),
            },
            "optional": {
                "trigger_in": ("STRING", {"forceInput": True}),
                "ollama_url": ("STRING", {"default": OLLAMA_DEFAULT_URL}),
            },
        }

    RETURN_TYPES = ("CONDITIONING", "STRING", "STRING")
    RETURN_NAMES = ("CONDITIONING", "enhanced_prompt", "trigger_out")
    OUTPUT_NODE = True
    FUNCTION = "enhance_and_encode"
    CATEGORY = "Boudoir Studio/Prompts"

    def enhance_and_encode(self, clip, prompt, ollama_model, system_prompt, enabled,
                           temperature, prepend_trigger, trigger_in=None, ollama_url=None):

        trigger_out = trigger_in.strip() if trigger_in else ""

        # Get enhanced prompt using the basic enhancer logic
        if not enabled or not prompt.strip():
            final_prompt = prompt.strip()
            if trigger_out:
                if prepend_trigger:
                    final_prompt = f"{trigger_out} {final_prompt}" if final_prompt else trigger_out
                else:
                    final_prompt = f"{final_prompt} {trigger_out}" if final_prompt else trigger_out
        else:
            # Enhance via Ollama
            server_url = ollama_url or OLLAMA_DEFAULT_URL
            try:
                print(f"[OllamaPromptEnhancerAdvanced] Enhancing with {ollama_model}...")

                request_data = {
                    "model": ollama_model,
                    "prompt": prompt.strip(),
                    "system": system_prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "top_p": 0.9}
                }

                req = urllib.request.Request(
                    f"{server_url}/api/generate",
                    data=json.dumps(request_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )

                with urllib.request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read().decode())
                    enhanced = data.get("response", "").strip()

                if not enhanced:
                    enhanced = prompt.strip()
                else:
                    print(f"[OllamaPromptEnhancerAdvanced] Enhanced ({len(prompt)} -> {len(enhanced)} chars)")

            except Exception as e:
                print(f"[OllamaPromptEnhancerAdvanced] Error: {e}")
                enhanced = prompt.strip()

            # Combine with trigger
            final_prompt = enhanced
            if trigger_out:
                if prepend_trigger:
                    final_prompt = f"{trigger_out} {enhanced}"
                else:
                    final_prompt = f"{enhanced} {trigger_out}"

        # Encode to CONDITIONING
        tokens = clip.tokenize(final_prompt)
        cond, pooled = clip.encode_from_tokens(tokens, return_pooled=True)
        conditioning = [[cond, {"pooled_output": pooled}]]

        return {"ui": {"text": [final_prompt]}, "result": (conditioning, final_prompt, trigger_out)}


class BoudoirSuperNode:
    """
    Boudoir Super-Node: Complete workflow node combining All-In-One functionality
    with Ollama prompt enhancement.

    Features:
    - CLIP/VAE loading (or pass-through from checkpoint)
    - LoRA loading with trigger word extraction
    - Resolution selection and latent creation
    - Random prompt from database OR manual prompt
    - Ollama-powered prompt enhancement (optional)
    - Full CONDITIONING output
    """

    RESOLUTIONS = [
        "1:1 - 1328x1328 (Square)",
        "16:9 - 1664x928 (Landscape)",
        "9:16 - 928x1664 (Portrait)",
        "4:3 - 1472x1104 (Landscape)",
        "3:4 - 1104x1472 (Portrait)",
        "3:2 - 1584x1056 (Landscape)",
        "2:3 - 1056x1584 (Portrait)",
    ]

    def __init__(self):
        self.loaded_loras = {}  # Cache for loaded LoRAs

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths
        gpu_options = get_available_gpus()
        ollama_models = get_ollama_models()
        lora_list = ["None"] + folder_paths.get_filename_list("loras")
        return {
            "required": {
                "model": ("MODEL",),
                "clip_name": (["None"] + folder_paths.get_filename_list("clip"), {"tooltip": "Select CLIP model (ignored if CLIP input connected)"}),
                "clip_device": (gpu_options, {"default": "auto", "tooltip": "GPU for CLIP model"}),
                "clip_type": (["stable_diffusion", "sd3", "flux", "flux2", "qwen_image", "hunyuan_image", "hidream", "ltxv", "pixart", "cosmos", "lumina2", "wan", "stable_cascade", "stable_audio", "mochi", "chroma", "ace", "omnigen2", "ovis"], {"default": "stable_diffusion", "tooltip": "CLIP type for the model architecture"}),
                "vae_name": (["None"] + folder_paths.get_filename_list("vae"), {"tooltip": "Select VAE (ignored if VAE input connected)"}),
                "vae_device": (gpu_options, {"default": "auto", "tooltip": "GPU for VAE model"}),
                "resolution": (cls.RESOLUTIONS, {"default": "1:1 - 1328x1328 (Square)"}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 64, "step": 1}),
                "use_random_prompt": ("BOOLEAN", {"default": False, "label_on": "Random Prompt", "label_off": "Manual Prompt"}),
                "prompt_category": (get_prompt_categories(), {"default": "any"}),
                "positive_prompt": ("STRING", {"default": "", "multiline": True, "placeholder": "Positive prompt (used when Manual Prompt selected)"}),
                "negative_prompt": ("STRING", {"default": "", "multiline": True, "placeholder": "Negative prompt"}),
                # === USER LORA (Slot 1) - Personal/Character LoRA ===
                "user_lora_enabled": ("BOOLEAN", {"default": True, "label_on": "User LoRA ON", "label_off": "User LoRA OFF", "tooltip": "Enable/disable user's personal LoRA"}),
                "user_lora_name": (lora_list, {"tooltip": "User's personal/character LoRA"}),
                "user_lora_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01, "tooltip": "User LoRA model strength"}),
                "user_lora_clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01, "tooltip": "User LoRA CLIP strength"}),
                # === STYLE LORA 1 (Slot 2) ===
                "style_lora1_enabled": ("BOOLEAN", {"default": False, "label_on": "Style 1 ON", "label_off": "Style 1 OFF", "tooltip": "Enable/disable style LoRA 1"}),
                "style_lora1_name": (lora_list, {"tooltip": "Style LoRA 1"}),
                "style_lora1_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "style_lora1_clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                # === STYLE LORA 2 (Slot 3) ===
                "style_lora2_enabled": ("BOOLEAN", {"default": False, "label_on": "Style 2 ON", "label_off": "Style 2 OFF", "tooltip": "Enable/disable style LoRA 2"}),
                "style_lora2_name": (lora_list, {"tooltip": "Style LoRA 2"}),
                "style_lora2_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "style_lora2_clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                # === NSFW LORA 1 (Slot 4) - Requires permission ===
                "nsfw_lora1_enabled": ("BOOLEAN", {"default": False, "label_on": "NSFW 1 ON", "label_off": "NSFW 1 OFF", "tooltip": "Enable/disable NSFW LoRA 1 (requires permission)"}),
                "nsfw_lora1_name": (lora_list, {"tooltip": "NSFW/Spicy LoRA 1"}),
                "nsfw_lora1_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "nsfw_lora1_clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                # === NSFW LORA 2 (Slot 5) - Requires permission ===
                "nsfw_lora2_enabled": ("BOOLEAN", {"default": False, "label_on": "NSFW 2 ON", "label_off": "NSFW 2 OFF", "tooltip": "Enable/disable NSFW LoRA 2 (requires permission)"}),
                "nsfw_lora2_name": (lora_list, {"tooltip": "NSFW/Spicy LoRA 2"}),
                "nsfw_lora2_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "nsfw_lora2_clip_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                # === Common settings ===
                "use_trigger": ("BOOLEAN", {"default": True, "label_on": "Add Trigger Words", "label_off": "No Triggers", "tooltip": "Extract and prepend trigger words from all enabled LoRAs"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "step": 1, "tooltip": "Seed for random prompt"}),
                "enhance_enabled": ("BOOLEAN", {"default": True, "label_on": "Enhance Prompt", "label_off": "No Enhancement", "tooltip": "Enable Ollama prompt enhancement"}),
                "ollama_model": (ollama_models, {"default": ollama_models[0] if ollama_models else "qwen2.5:latest", "tooltip": "Ollama model for enhancement"}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.1, "tooltip": "Enhancement temperature"}),
                "system_prompt": ("STRING", {"multiline": True, "default": SUPERNODE_SYSTEM_PROMPT, "tooltip": "System prompt for enhancement"}),
                "extra_triggers": ("STRING", {"default": "", "multiline": False, "placeholder": "Extra trigger words from upstream LoRAs", "tooltip": "Additional trigger words to prepend (from LoRAs loaded before this node)"}),
            },
            "optional": {
                "clip_in": ("CLIP", {"tooltip": "Optional CLIP from checkpoint loader"}),
                "vae_in": ("VAE", {"tooltip": "Optional VAE from checkpoint loader"}),
                "ollama_url": ("STRING", {"default": OLLAMA_DEFAULT_URL, "tooltip": "Ollama server URL"}),
            },
            "hidden": {
                "extra_pnginfo": "EXTRA_PNGINFO",
            },
        }

    RETURN_TYPES = ("MODEL", "CLIP", "LATENT", "CONDITIONING", "CONDITIONING", "VAE", "STRING", "STRING", "STRING", "STRING")
    RETURN_NAMES = ("MODEL", "CLIP", "LATENT", "POSITIVE", "NEGATIVE", "VAE", "prompt_text", "enhanced_text", "trigger_words", "prompt_id")
    OUTPUT_NODE = True
    FUNCTION = "process"
    CATEGORY = "Boudoir Studio"

    @classmethod
    def IS_CHANGED(cls, use_random_prompt, seed, enhance_enabled, **kwargs):
        if use_random_prompt or enhance_enabled:
            return seed
        return ""

    def process(self, model, clip_name, clip_device, clip_type, vae_name, vae_device, resolution, batch_size,
                use_random_prompt, prompt_category, positive_prompt, negative_prompt,
                user_lora_enabled, user_lora_name, user_lora_strength, user_lora_clip_strength,
                style_lora1_enabled, style_lora1_name, style_lora1_strength, style_lora1_clip_strength,
                style_lora2_enabled, style_lora2_name, style_lora2_strength, style_lora2_clip_strength,
                nsfw_lora1_enabled, nsfw_lora1_name, nsfw_lora1_strength, nsfw_lora1_clip_strength,
                nsfw_lora2_enabled, nsfw_lora2_name, nsfw_lora2_strength, nsfw_lora2_clip_strength,
                use_trigger, seed,
                enhance_enabled, ollama_model, temperature, system_prompt, extra_triggers,
                clip_in=None, vae_in=None, ollama_url=None, extra_pnginfo=None):
        # Record workflow start time for generation timing
        global _workflow_start_time
        import time as time_module
        _workflow_start_time = time_module.time()
        print(f"[BoudoirSuperNode] Workflow started at {_workflow_start_time:.2f}")
        
        import torch
        import folder_paths
        import comfy.utils
        import comfy.sd
        import comfy.model_management

        def parse_device(device_str):
            if device_str == "auto" or not device_str:
                return None
            return device_str.split(" ")[0]

        clip_dev = parse_device(clip_device)
        vae_dev = parse_device(vae_device)

        # === CLIP: Use input if connected, otherwise load ===
        clip = None
        if clip_in is not None:
            clip = clip_in
        elif clip_name and clip_name != "None":
            clip_path = folder_paths.get_full_path_or_raise("clip", clip_name)
            model_options = {}
            if clip_dev:
                model_options["load_device"] = torch.device(clip_dev)
            # Convert clip_type string to CLIPType enum
            clip_type_enum = getattr(comfy.sd.CLIPType, clip_type.upper(), comfy.sd.CLIPType.STABLE_DIFFUSION)
            clip = comfy.sd.load_clip(ckpt_paths=[clip_path],
                                       embedding_directory=folder_paths.get_folder_paths("embeddings"),
                                       clip_type=clip_type_enum,
                                       model_options=model_options)

        # === VAE: Use input if connected, otherwise load ===
        vae = None
        if vae_in is not None:
            vae = vae_in
        elif vae_name and vae_name != "None":
            vae_path = folder_paths.get_full_path_or_raise("vae", vae_name)
            vae_sd = comfy.utils.load_torch_file(vae_path)
            if vae_dev:
                vae = comfy.sd.VAE(sd=vae_sd, device=torch.device(vae_dev))
            else:
                vae = comfy.sd.VAE(sd=vae_sd)

        # === Apply LoRAs (5 slots) and extract triggers ===
        model_lora = model
        clip_lora = clip
        trigger_list = []

        # Define all 5 LoRA slots
        lora_slots = [
            ("User LoRA", user_lora_enabled, user_lora_name, user_lora_strength, user_lora_clip_strength),
            ("Style 1", style_lora1_enabled, style_lora1_name, style_lora1_strength, style_lora1_clip_strength),
            ("Style 2", style_lora2_enabled, style_lora2_name, style_lora2_strength, style_lora2_clip_strength),
            ("NSFW 1", nsfw_lora1_enabled, nsfw_lora1_name, nsfw_lora1_strength, nsfw_lora1_clip_strength),
            ("NSFW 2", nsfw_lora2_enabled, nsfw_lora2_name, nsfw_lora2_strength, nsfw_lora2_clip_strength),
        ]

        for slot_name, enabled, lora_name, strength_model, strength_clip in lora_slots:
            if not enabled or not lora_name or lora_name == "None":
                continue
            if strength_model == 0 and strength_clip == 0:
                continue

            try:
                lora_path = folder_paths.get_full_path_or_raise("loras", lora_name)

                # Use cached LoRA if available
                if lora_path in self.loaded_loras:
                    lora = self.loaded_loras[lora_path]
                else:
                    lora = comfy.utils.load_torch_file(lora_path, safe_load=True)
                    self.loaded_loras[lora_path] = lora

                # Apply LoRA to model and clip
                model_lora, clip_lora = comfy.sd.load_lora_for_models(
                    model_lora, clip_lora, lora, strength_model, strength_clip
                )
                print(f"[BoudoirSuperNode] Loaded {slot_name}: {lora_name} (model={strength_model}, clip={strength_clip})")

                # Extract trigger word
                if use_trigger:
                    trigger = self._extract_trigger(lora_name)
                    if trigger.strip():
                        trigger_list.append(trigger.strip())

            except Exception as e:
                print(f"[BoudoirSuperNode] Error loading {slot_name} ({lora_name}): {e}")
                continue

        # Combine all trigger words
        trigger_words = ", ".join(trigger_list) if trigger_list else ""

        # === Get prompt (random or manual) ===
        prompt_id = ""
        if use_random_prompt:
            base_prompt, prompt_id = self._get_random_prompt(prompt_category)
        else:
            base_prompt = positive_prompt

        # === Enhance prompt via Ollama (if enabled) ===
        enhanced_prompt = base_prompt
        if enhance_enabled and base_prompt.strip():
            server_url = ollama_url or OLLAMA_DEFAULT_URL
            try:
                print(f"[BoudoirSuperNode] Enhancing prompt with {ollama_model}...")

                request_data = {
                    "model": ollama_model,
                    "prompt": base_prompt.strip(),
                    "system": system_prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "top_p": 0.9}
                }

                req = urllib.request.Request(
                    f"{server_url}/api/generate",
                    data=json.dumps(request_data).encode('utf-8'),
                    headers={'Content-Type': 'application/json'}
                )

                with urllib.request.urlopen(req, timeout=60) as response:
                    data = json.loads(response.read().decode())
                    enhanced_prompt = data.get("response", "").strip()

                if not enhanced_prompt:
                    print("[BoudoirSuperNode] Empty response, using original")
                    enhanced_prompt = base_prompt
                else:
                    print(f"[BoudoirSuperNode] Enhanced ({len(base_prompt)} -> {len(enhanced_prompt)} chars)")

            except Exception as e:
                print(f"[BoudoirSuperNode] Enhancement error: {e}")
                enhanced_prompt = base_prompt

        # Prepend trigger words to enhanced prompt (internal LoRAs + extra upstream triggers)
        final_prompt = enhanced_prompt
        all_triggers = []
        if trigger_words.strip():
            all_triggers.append(trigger_words.strip())
        if extra_triggers.strip():
            all_triggers.append(extra_triggers.strip())
        if all_triggers:
            final_prompt = f"{' '.join(all_triggers)} {enhanced_prompt}"

        # === Create latent ===
        dimensions = resolution.split(" - ")[1].split(" ")[0]
        width, height = map(int, dimensions.split("x"))
        latent = torch.zeros([batch_size, 4, height // 8, width // 8])

        # === Encode prompts ===
        positive_cond = None
        negative_cond = None
        if clip_lora is not None:
            tokens_pos = clip_lora.tokenize(final_prompt)
            cond_pos, pooled_pos = clip_lora.encode_from_tokens(tokens_pos, return_pooled=True)
            positive_cond = [[cond_pos, {"pooled_output": pooled_pos}]]

            tokens_neg = clip_lora.tokenize(negative_prompt)
            cond_neg, pooled_neg = clip_lora.encode_from_tokens(tokens_neg, return_pooled=True)
            negative_cond = [[cond_neg, {"pooled_output": pooled_neg}]]

        # Inject enhanced prompt into extra_pnginfo for all save nodes
        if extra_pnginfo is not None:
            extra_pnginfo["enhanced_display"] = final_prompt
            print(f"[BoudoirSuperNode] Injected enhanced_display into metadata ({len(final_prompt)} chars)")

        return {
            "ui": {"text": [final_prompt]},
            "result": (model_lora, clip_lora, {"samples": latent}, positive_cond, negative_cond, vae, base_prompt, final_prompt, trigger_words, prompt_id)
        }

    def _extract_trigger(self, lora_name):
        """Extract trigger word from LoRA metadata"""
        try:
            from safetensors import safe_open
            import folder_paths

            lora_path = folder_paths.get_full_path("loras", lora_name)
            if not lora_path or not os.path.exists(lora_path):
                return ""

            with safe_open(lora_path, framework='pt') as f:
                meta = f.metadata()

            if not meta:
                return ""

            trigger_word = meta.get('modelspec.trigger_phrase', '')

            if not trigger_word and 'ss_tag_frequency' in meta:
                try:
                    tags_data = json.loads(meta['ss_tag_frequency'])
                    all_tags = {}
                    for dataset, tag_dict in tags_data.items():
                        for tag, count in tag_dict.items():
                            tag_clean = tag.strip()
                            if tag_clean:
                                all_tags[tag_clean] = all_tags.get(tag_clean, 0) + count

                    if all_tags:
                        sorted_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)
                        trigger_word = sorted_tags[0][0]
                except json.JSONDecodeError:
                    pass

            if not trigger_word:
                trigger_word = meta.get('ss_output_name', '')

            return trigger_word

        except Exception as e:
            print(f"[BoudoirSuperNode] Trigger extraction error: {e}")
            return ""

    def _get_random_prompt(self, category):
        """Fetch random prompt from Boudoir API"""
        try:
            url = f"{API_BASE_URL}/random"
            if category != "any":
                url += f"?category={urllib.parse.quote(category)}"

            req = urllib.request.Request(url)
            req.add_header('Content-Type', 'application/json')

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())

            if data.get("success") and data.get("prompt"):
                prompt_text = data["prompt"].get("text", "")
                prompt_id = str(data["prompt"].get("id", ""))
                return (prompt_text, prompt_id)

            return ("", "")

        except Exception as e:
            print(f"[BoudoirSuperNode] Random prompt error: {e}")
            return ("", "")


# Node mappings for ComfyUI
class BoudoirSeed:
    """
    Seed generator with selectable bit depth (32-bit or 64-bit).
    Use 32-bit for compatibility with nodes that use numpy random (like SeedVR2VideoUpscaler).
    Use 64-bit for nodes that support larger seed ranges.
    """

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xffffffffffffffff,
                    "step": 1,
                    "display": "number"
                }),
                "bit_depth": (["32-bit (numpy compatible)", "64-bit (full range)"], {
                    "default": "32-bit (numpy compatible)"
                }),
                "mode": (["fixed", "randomize", "increment", "decrement"], {
                    "default": "randomize"
                }),
            },
        }

    RETURN_TYPES = ("INT", "INT", "STRING")
    RETURN_NAMES = ("seed", "seed_64bit", "seed_info")
    FUNCTION = "generate_seed"
    CATEGORY = "Boudoir Studio/Utils"

    @classmethod
    def IS_CHANGED(cls, seed, bit_depth, mode):
        if mode == "randomize":
            return random.random()
        return seed

    def generate_seed(self, seed, bit_depth, mode):
        # Generate new seed based on mode
        if mode == "randomize":
            if "32-bit" in bit_depth:
                new_seed = random.randint(0, 0xFFFFFFFF)
            else:
                new_seed = random.randint(0, 0xFFFFFFFFFFFFFFFF)
        elif mode == "increment":
            new_seed = seed + 1
        elif mode == "decrement":
            new_seed = max(0, seed - 1)
        else:  # fixed
            new_seed = seed

        # Calculate both versions
        seed_32bit = new_seed % (2**32)
        seed_64bit = new_seed

        # Select output based on bit depth
        if "32-bit" in bit_depth:
            output_seed = seed_32bit
        else:
            output_seed = seed_64bit

        info = f"Mode: {mode}, Depth: {bit_depth}\n32-bit: {seed_32bit}\n64-bit: {seed_64bit}"

        return (output_seed, seed_64bit, info)


NODE_CLASS_MAPPINGS = {
    "BoudoirPromptSearch": BoudoirPromptSearch,
    "BoudoirRandomPrompt": BoudoirRandomPrompt,
    "BoudoirPromptById": BoudoirPromptById,
    "BoudoirPromptCategories": BoudoirPromptCategories,
    "BoudoirPromptSearchWidget": BoudoirPromptSearchWidget,
    "LoRATriggerWordExtractor": LoRATriggerWordExtractor,
    "LoRATriggerWordFromLoader": LoRATriggerWordFromLoader,
    "LoRALoaderWithTrigger": LoRALoaderWithTrigger,
    "LoRALoaderModelClipWithTrigger": LoRALoaderModelClipWithTrigger,
    "MultiLoRALoaderWithTriggers": MultiLoRALoaderWithTriggers,
    "PowerLoRALoaderWithTriggers": PowerLoRALoaderWithTriggers,
    "LoRAFolderLoaderWithTrigger": LoRAFolderLoaderWithTrigger,
    "LoRAFolderLoaderModelClipWithTrigger": LoRAFolderLoaderModelClipWithTrigger,
    "BoudoirAllInOneNode": BoudoirAllInOneNode,
    "BoudoirSaveImageWithText": BoudoirSaveImageWithText,
    "BoudoirSaveText": BoudoirSaveText,
    "BoudoirLatentResolutionSelector": BoudoirLatentResolutionSelector,
    "ZImageResolutionSelector": ZImageResolutionSelector,
    "OllamaPromptEnhancer": OllamaPromptEnhancer,
    "OllamaPromptEnhancerAdvanced": OllamaPromptEnhancerAdvanced,
    "BoudoirSuperNode": BoudoirSuperNode,
    "BoudoirSeed": BoudoirSeed,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BoudoirPromptSearch": "Boudoir Search Prompt Library",
    "BoudoirRandomPrompt": "Boudoir Random Prompt",
    "BoudoirPromptById": "Boudoir Get Prompt by ID",
    "BoudoirPromptCategories": "Boudoir List Categories",
    "BoudoirPromptSearchWidget": "Boudoir Search & Select Prompt",
    "LoRATriggerWordExtractor": "Boudoir LoRA Trigger Word (Path)",
    "LoRATriggerWordFromLoader": "Boudoir LoRA Trigger Word (Dropdown)",
    "LoRALoaderWithTrigger": "Boudoir Load LoRA + Trigger (Model)",
    "LoRALoaderModelClipWithTrigger": "Boudoir Load LoRA + Trigger (Model+CLIP)",
    "MultiLoRALoaderWithTriggers": "Boudoir Multi-LoRA Loader (5x) + Triggers",
    "PowerLoRALoaderWithTriggers": "Boudoir Power LoRA Loader + Triggers",
    "LoRAFolderLoaderWithTrigger": "Boudoir Load LoRA (Folder) + Trigger (Model)",
    "LoRAFolderLoaderModelClipWithTrigger": "Boudoir Load LoRA (Folder) + Trigger (Model+CLIP)",
    "BoudoirAllInOneNode": "Boudoir All-In-One",
    "BoudoirSaveImageWithText": "Boudoir Save Image + Text",
    "BoudoirSaveText": "Boudoir Save Text",
    "BoudoirLatentResolutionSelector": "Boudoir Latent Resolution Selector",
    "ZImageResolutionSelector": "Boudoir Z-Image Resolution Selector",
    "OllamaPromptEnhancer": "Boudoir Prompt Enhancer",
    "OllamaPromptEnhancerAdvanced": "Boudoir Prompt Enhancer (CONDITIONING)",
    "BoudoirSuperNode": "Boudoir Super-Node",
    "BoudoirSeed": "Boudoir Seed (32/64-bit)",
}
