"""Render the pinned template with the serving engine's MiniJinja version.

The Rust frontend uses MiniJinja, not Python Jinja. Scalar spelling matters:
``none`` and ``None`` can have equal lengths but different token IDs.
Prompt-bearing numbers are restricted by serving_profile to signed integers;
Python/serde_json floating-point formatting is deliberately not approximated.
"""

import json

from serving_profile import AUTO_PARALLEL_FLAG, require


def hf_tojson(value, **kwargs):
    """Match Rust hf_tojson's qualified JSON subset and default separators."""
    import minijinja

    require(not (kwargs.keys() - {"ensure_ascii", "sort_keys", "indent", "separators"}),
            "Unsupported tojson filter argument")
    options = {"ensure_ascii": False, "sort_keys": False, "allow_nan": False, **kwargs}
    return minijinja.safe(json.dumps(value, **options))


def render_prompt(template, normalized, bos_token=None, eos_token=None):
    import minijinja

    environment = minijinja.Environment(
        trim_blocks=True,
        lstrip_blocks=True,
        pycompat=True,
        filters={"tojson": hf_tojson},
    )
    context = {
        "messages": normalized["messages"],
        "add_generation_prompt": True,
        "continue_final_message": False,
        **normalized["chat_template_kwargs"],
    }
    if normalized.get("tools"):
        context["tools"] = normalized["tools"]
        context[AUTO_PARALLEL_FLAG] = True
    if bos_token is not None:
        context["bos_token"] = bos_token
    if eos_token is not None:
        context["eos_token"] = eos_token
    # Matches Rust load_chat_template for a .jinja file.
    loaded = template.strip().replace("\\n", "\n")
    try:
        return environment.render_str(loaded, **context)
    except minijinja.TemplateError as exc:
        raise ValueError("Request cannot be rendered by the pinned serving template") from exc
