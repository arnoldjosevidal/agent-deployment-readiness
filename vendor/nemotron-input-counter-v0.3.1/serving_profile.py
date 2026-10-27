"""Bounded, source-derived request normalization; no network or inference."""

import copy
import json
import math
import re


MODEL = "nvidia/Nemotron-3_5-Lightning"
STATUS = "verified-bounded-profile"
PROFILE_ID = "nemotron-lightning-input-v2"
AUTO_PARALLEL_FLAG = "vllm_nemotron_3_5_lightning_auto_parallel_tool_request"
RENDERING_KWARGS = frozenset({"enable_thinking", "force_nonempty_content"})
CONTROL_MARKERS = (
    "<tool_call>", "</tool_call>", "<tool_response>", "</tool_response>",
    "<|im_start|>", "<|im_end|>",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def _tool_argument_integer(value):
    # Raw tool-argument strings reach the engine's JSON decoder unchanged.
    # Rust serde_json preserves lexical -0 as a float; Python int would erase
    # its sign before the prompt-number validator can refuse it. Limit this
    # guard to raw arguments: outer request JSON is normalized by the gateway.
    require(value != "-0", "Tool arguments: negative zero is outside the qualified integer subset")
    return int(value)


def load_json(text, *, tool_arguments=False):
    """Reject duplicate/non-finite values; preserve the raw-argument numeric boundary."""
    value = json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant,
                       parse_int=_tool_argument_integer if tool_arguments else int)
    validate_json(value)
    return value


def validate_json(value, path="request", prompt_bearing=False):
    """Bound prompt numerics to the qualified integer subset, without coercion."""
    if value is None or type(value) in {str, bool}:
        if type(value) is str:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError(f"{path}: unpaired Unicode surrogate") from exc
        return
    if type(value) is int:
        if prompt_bearing:
            require(-(1 << 63) <= value <= (1 << 63) - 1, f"{path}: prompt integers must fit i64")
        return
    if type(value) is float:
        require(math.isfinite(value), f"{path}: non-finite number")
        require(not prompt_bearing, f"{path}: floating-point prompt values are not qualified")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            validate_json(item, f"{path}[{index}]", prompt_bearing)
        return
    require(type(value) is dict, f"{path}: expected a JSON value")
    for key, item in value.items():
        require(type(key) is str, f"{path}: JSON object keys must be strings")
        validate_json(key, f"{path} key")
        validate_json(item, f"{path}.{key}", prompt_bearing)


def _name(value, label):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value),
            f"{label}: function name must contain 1–64 letters, digits, underscores or dashes")
    return value


def normalize_tools(tools):
    require(type(tools) is list and tools, "tools must be a nonempty list")
    normalized = []
    names = set()
    for index, tool in enumerate(tools):
        label = f"Tool {index}"
        require(type(tool) is dict and not (tool.keys() - {"type", "function"}), f"{label}: unsupported fields")
        require(tool.get("type", "function") == "function", f"{label}: only function tools are supported")
        function = tool.get("function")
        require(type(function) is dict and not (function.keys() - {"name", "description", "parameters", "strict"}),
                f"{label}: unsupported function fields")
        name = _name(function.get("name"), label)
        require(name not in names, f"{label}: duplicate function name")
        names.add(name)
        description = function.get("description")
        require(description is None or type(description) is str, f"{label}: description must be a string or null")
        parameters = function.get("parameters")
        require(type(parameters) is dict, f"{label}: parameters must be an object")
        validate_json(parameters, f"{label}.parameters", prompt_bearing=True)
        if "properties" in parameters:
            properties = parameters["properties"]
            require(type(properties) is dict, f"{label}: parameters.properties must be an object")
            for name_, fields in properties.items():
                require(type(fields) is dict, f"{label}: property {name_!r} must be an object")
                # These two fields go through scalar |string / |trim rather
                # than the JSON filter. Collection forms are not qualified.
                for key in ("type", "description"):
                    if key in fields:
                        require(type(fields[key]) is str, f"{label}: property {name_!r}.{key} must be a string")
        strict = function.get("strict")
        require(strict is None or type(strict) is bool, f"{label}: strict must be boolean or null")
        # Rust TemplateToolDefinition serializes these four fields in this order,
        # including absent optional values as null. Never sort schema keys.
        normalized.append({"type": "function", "function": {
            "name": name, "description": description,
            "parameters": copy.deepcopy(parameters), "strict": strict,
        }})
    return normalized


def decode_tool_arguments(messages):
    """Decode raw wire-format argument strings exactly once in a private copy."""
    copied = copy.deepcopy(messages)
    require(type(copied) is list, "messages must be a list")
    for index, message in enumerate(copied):
        if type(message) is not dict or "tool_calls" not in message:
            continue
        calls = message["tool_calls"]
        if calls is None:
            continue
        require(type(calls) is list, f"Message {index}: tool_calls must be a list")
        for call in calls:
            require(type(call) is dict and type(call.get("function")) is dict,
                    f"Message {index}: malformed tool call")
            function = call["function"]
            # Rust can default missing arguments, but the public gateway's
            # FunctionCall.arguments is a required string before that stage.
            raw = function.get("arguments")
            require(type(raw) is str, f"Message {index}: wire tool arguments must be a JSON string")
            arguments = load_json(raw, tool_arguments=True)
            require(type(arguments) is dict, f"Message {index}: tool arguments must decode to an object")
            validate_json(arguments, f"Message {index}.arguments", prompt_bearing=True)
            function["arguments"] = arguments
    return copied


def _content(content, label, allow_thinking=False, allow_empty=False):
    require(type(content) is str, f"{label}: content must be a string")
    require(allow_empty or bool(content), f"{label}: empty content is outside this profile")
    forbidden = CONTROL_MARKERS + (() if allow_thinking else ("<think>", "</think>"))
    require(not any(marker in content for marker in forbidden), f"{label}: unsupported control markup")
    return content


def normalize_messages(messages, tools_enabled):
    require(type(messages) is list and messages, "messages must be a nonempty list")
    require(len(messages) <= 100, "Counter supports at most 100 messages")
    normalized = []
    state = "user"
    pending = set()
    seen_ids = set()
    for index, message in enumerate(messages):
        label = f"Message {index}"
        require(type(message) is dict, f"{label}: expected an object")
        allowed = {"role", "content", "tool_calls", "tool_call_id"} if tools_enabled else {"role", "content"}
        require(not (message.keys() - allowed), f"{label}: unsupported fields")
        role = message.get("role")
        content = message.get("content")
        if role == "system":
            require(index == 0 and set(message) == {"role", "content"}, f"{label}: system is allowed only first")
            normalized.append({"role": role, "content": _content(content, label)})
            continue
        if role == "user":
            require(state == "user" and set(message) == {"role", "content"}, f"{label}: unexpected user message")
            normalized.append({"role": role, "content": _content(content, label)})
            state = "assistant"
            continue
        if role == "assistant":
            require(state == "assistant" and "tool_call_id" not in message, f"{label}: unexpected assistant message")
            calls = message.get("tool_calls")
            require(calls is None or type(calls) is list, f"{label}: tool_calls must be a list or null")
            if not calls:
                require(not (set(message) - {"role", "content", "tool_calls"}), f"{label}: unsupported fields")
                normalized.append({"role": role, "content": _content(content, label, allow_thinking=tools_enabled)})
                state = "user"
                continue
            require(tools_enabled, f"{label}: tool history requires tools")
            content = "" if content is None else content
            normalized_calls = []
            for call in calls:
                require(type(call) is dict and not (call.keys() - {"id", "type", "function"}), f"{label}: unsupported tool call fields")
                require(call.get("type", "function") == "function", f"{label}: only function calls are supported")
                call_id = call.get("id")
                require(type(call_id) is str and call_id and call_id not in seen_ids, f"{label}: missing or duplicate tool call id")
                seen_ids.add(call_id)
                pending.add(call_id)
                function = call.get("function")
                require(type(function) is dict and set(function) == {"name", "arguments"}, f"{label}: unsupported tool function fields")
                name = _name(function.get("name"), label)
                arguments = function["arguments"]
                require(type(arguments) is dict, f"{label}: normalized tool arguments must be an object")
                validate_json(arguments, f"{label}.arguments", prompt_bearing=True)
                normalized_calls.append({"id": call_id, "type": "function", "function": {
                    "name": name, "arguments": copy.deepcopy(arguments),
                }})
            normalized.append({"role": role, "content": _content(content, label, allow_thinking=True, allow_empty=True), "tool_calls": normalized_calls})
            state = "tool"
            continue
        if role == "tool":
            require(tools_enabled and state == "tool" and set(message) == {"role", "content", "tool_call_id"}, f"{label}: unexpected tool result")
            call_id = message.get("tool_call_id")
            require(type(call_id) is str and call_id in pending, f"{label}: unpaired or duplicate tool result")
            pending.remove(call_id)
            normalized.append({"role": role, "content": _content(content, label, allow_empty=True), "tool_call_id": call_id})
            if not pending:
                state = "assistant"
            continue
        raise ValueError(f"{label}: unsupported role")
    require(not pending, "Every assistant tool call requires exactly one tool result before counting")
    require(normalized[-1]["role"] in ({"user", "tool"} if tools_enabled else {"user"}),
            "Conversation must end with a user message or a complete tool-result round; no assistant prefill")
    return normalized


def normalize_request(request):
    """Validate canonical rendering input; tool argument objects are already decoded."""
    require(type(request) is dict, "Rendering input must be an object")
    validate_json(request)
    require(not (request.keys() - {"model", "messages", "chat_template_kwargs", "tools", "tool_choice"}), "Unsupported rendering input fields")
    require(request.get("model") == MODEL, f"Only model={MODEL!r} is supported")
    tools = request.get("tools")
    require(tools is None or type(tools) is list, "tools must be a list or null")
    enabled = bool(tools)
    choice = request.get("tool_choice")
    require(choice is None or choice == "auto", "Only omitted or auto tool_choice is qualified")
    kwargs = request.get("chat_template_kwargs", {})
    require(type(kwargs) is dict and not (kwargs.keys() - RENDERING_KWARGS), "Unsupported rendering kwargs")
    require(all(type(value) is bool for value in kwargs.values()), "Rendering kwargs must be boolean")
    # The current source profile has no server override for these defaults.
    # Protocol-owned auto-parallel metadata is injected only by the renderer.
    effective = {"enable_thinking": not enabled, "force_nonempty_content": True, **kwargs}
    normalized = {
        "model": MODEL,
        "messages": normalize_messages(request.get("messages"), enabled),
        "chat_template_kwargs": effective,
    }
    if enabled:
        normalized["tools"] = normalize_tools(tools)
        normalized["tool_choice"] = "auto"
    return normalized
