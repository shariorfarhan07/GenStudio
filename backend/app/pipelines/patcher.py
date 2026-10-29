"""
Graph patcher — injects user parameters into a copy of the ComfyUI workflow.

Rules:
- Works on a deep copy, never mutating the template.
- Uploads images to ComfyUI and writes the returned filename.
- Snaps resolution to multiple_of constraints.
- Snaps frame count to frame rules (4n+1 or 8n+1).
- Inserts LoRA chain nodes and rewires links.
- Randomises seed when value is -1.
"""
from __future__ import annotations

import copy
import logging
import math
import random
from typing import Any

from app.engine.client import comfy_client
from app.pipelines.registry import PipelineManifest

logger = logging.getLogger(__name__)


def snap_to_multiple(value: int, multiple: int) -> int:
    return max(multiple, round(value / multiple) * multiple)


def snap_frames(frames: int, rule: str) -> int:
    """Snap frames to 4n+1 or 8n+1 so the model never gets an invalid count."""
    if rule == "4n+1":
        n = max(1, round((frames - 1) / 4))
        return 4 * n + 1
    if rule == "8n+1":
        n = max(1, round((frames - 1) / 8))
        return 8 * n + 1
    return frames


def fit_resolution(
    src_w: int, src_h: int, target_pixels: int, multiple: int
) -> tuple[int, int]:
    """Scale src resolution to ~target_pixels preserving aspect, snapped."""
    ratio = src_w / src_h
    h = math.sqrt(target_pixels / ratio)
    w = h * ratio
    w = snap_to_multiple(round(w), multiple)
    h = snap_to_multiple(round(h), multiple)
    return w, h


def _set_node_input(graph: dict, node_id: str, input_name: str, value: Any) -> None:
    node = graph.get(node_id)
    if not node:
        logger.warning("Node %s not found in graph", node_id)
        return
    node.setdefault("inputs", {})[input_name] = value


async def patch_workflow(
    manifest: PipelineManifest,
    params: dict[str, Any],
    job_id: str,
    loras: list[dict] | None = None,
    image_bytes: bytes | None = None,
    image_filename: str = "input.png",
) -> dict[str, Any]:
    """
    Returns a patched deep copy of the manifest workflow ready for submission.
    """
    graph = manifest.load_workflow()
    graph = copy.deepcopy(graph)

    # Upload image if provided
    if image_bytes is not None:
        stored_name = await comfy_client.upload_image(image_bytes, image_filename)
        # Find image param and inject
        for pname, pmeta in manifest.params.items():
            if pmeta.get("type") in ("image", "video"):
                node_id = str(pmeta.get("node", ""))
                input_name = pmeta.get("input", "image")
                _set_node_input(graph, node_id, input_name, stored_name)

    # Apply resolution tier whenever one is requested and the user gave no explicit size
    tier_name = params.get("_tier", "")
    tier = manifest.tiers.get(tier_name) if tier_name else None
    if tier:
        for key, tkey in (("width", "w"), ("height", "h"), ("frames", "frames")):
            if tkey in tier and key in manifest.params:
                params.setdefault(key, tier[tkey])

    # Fit resolution to the source image aspect ratio if size is still unset
    if image_bytes and any(
        pmeta.get("type") == "int" and pname in ("width", "height")
        for pname, pmeta in manifest.params.items()
    ):
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(image_bytes))
            src_w, src_h = img.size
        except Exception:
            src_w, src_h = None, None

        if src_w and src_h and ("width" not in params or "height" not in params):
            ref_tier = tier or next(iter(manifest.tiers.values()), {})
            target_pixels = ref_tier.get("w", 832) * ref_tier.get("h", 480)
            multiple = 16
            for pname in ("width", "height"):
                if pname in manifest.params:
                    multiple = manifest.params[pname].get("multiple_of", 16)
                    break
            w, h = fit_resolution(src_w, src_h, target_pixels, multiple)
            params.setdefault("width", w)
            params.setdefault("height", h)

    # Inject each param
    for pname, pmeta in manifest.params.items():
        if pmeta.get("type") in ("image", "video"):
            continue  # file params handled above
        if pname.startswith("_"):
            continue

        value = params.get(pname, pmeta.get("default"))
        if value is None:
            continue

        ptype = pmeta.get("type", "text")

        # Seed: randomize if -1
        if ptype == "seed" and value == -1:
            value = random.randint(0, 2**32 - 1)

        # Snap int values
        if ptype == "int":
            value = int(value)
            multiple = pmeta.get("multiple_of")
            if multiple:
                value = snap_to_multiple(value, multiple)
            rule = pmeta.get("rule")
            if rule:
                value = snap_frames(value, rule)
            mn = pmeta.get("min")
            mx = pmeta.get("max")
            if mn is not None:
                value = max(int(mn), value)
            if mx is not None:
                value = min(int(mx), value)

        # Single node injection
        node_id = pmeta.get("node")
        if node_id:
            input_name = pmeta.get("input", pname)
            _set_node_input(graph, str(node_id), input_name, value)

        for ref in pmeta.get("split_at", []):
            nid, iname = ref.split(".")
            _set_node_input(graph, nid, iname, int(value) // 2)

        # Multi-node injection (e.g. steps across both MoE expert samplers)
        for ref in pmeta.get("nodes", []):
            nid, iname = ref.split(".") if "." in ref else (ref, pname)
            _set_node_input(graph, str(nid), iname, value)

    # Set output filename prefix
    for node in graph.values():
        if node.get("class_type") in ("SaveImage", "SaveVideo", "VHS_VideoCombine",
                                      "SaveAnimatedWEBP", "SaveAnimatedPNG"):
            node.setdefault("inputs", {})["filename_prefix"] = f"job_{job_id}"

    # LoRA chain injection
    if loras:
        graph = _inject_loras(graph, manifest.lora_points, loras)

    return graph


def _inject_loras(
    graph: dict[str, Any],
    lora_points: list[dict],
    loras: list[dict],
) -> dict[str, Any]:
    """
    Insert LoraLoaderModelOnly nodes after each lora_point and rewire
    the model link to pass through them.
    """
    if not lora_points or not loras:
        return graph

    # Find next unused node id
    max_id = max((int(k) for k in graph.keys() if k.isdigit()), default=100)
    new_lora_ids: set[str] = set()

    for point in lora_points:
        after_node_id = str(point.get("after", ""))
        if after_node_id not in graph:
            continue

        # The output of after_node becomes the input to the first LoRA
        current_source = [after_node_id, 0]  # [node_id, output_slot]

        for lora in loras:
            max_id += 1
            new_id = str(max_id)
            graph[new_id] = {
                "class_type": "LoraLoaderModelOnly",
                "inputs": {
                    "model": current_source,
                    "lora_name": lora["file"],
                    "strength_model": lora.get("weight", 1.0),
                },
            }
            new_lora_ids.add(new_id)
            current_source = [new_id, 0]

        # Find all nodes that reference after_node_id slot 0 for model input
        for nid, node in graph.items():
            if nid in new_lora_ids:
                continue
            for iname, ival in list(node.get("inputs", {}).items()):
                if (
                    isinstance(ival, list)
                    and len(ival) == 2
                    and str(ival[0]) == after_node_id
                    and ival[1] == 0
                    and iname in ("model", "unet", "model_b")
                ):
                    # Rewire to the last LoRA node
                    node["inputs"][iname] = current_source

    return graph
