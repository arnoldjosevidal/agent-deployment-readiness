# Bounded request contract

## Request and defaults

- Exact model: `nvidia/Nemotron-3_5-Lightning`.
- Use `count_request.py` or `evaluate_request` for raw API requests. `count_chat.py` accepts the normalized internal projection instead.
- Up to 100 messages. Optional first system message; complete user/assistant turns and supported tool-call/result rounds. Input must end with a user message or a completed tool-result round, never an assistant prefill.
- Text content only. User/system content must be nonempty strings. A tool-call assistant may have empty/null content. Tool results may be empty strings. Separate `reasoning`, `reasoning_content` and `thinking` fields are rejected.
- `tools` may be absent/null/empty for text-only counting, or a list of function definitions. Only omitted or `"auto"` `tool_choice` is supported. Omit `parallel_tool_calls`; explicit values are not qualified through the public gateway profile.
- Supported template kwargs: boolean `enable_thinking` and `force_nonempty_content`. The server default `force_nonempty_content=true` is included. Omitted `enable_thinking` is false for auto tools and true without tools. An explicit supported kwarg takes precedence over `reasoning_effort`; otherwise effort `none` disables thinking and the supported other efforts enable it.
- Supported efforts: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. This describes input rendering, not a promised output reasoning budget.
- A literal `extra_body` may contain only supported extras. It overrides top-level extras by a **shallow** merge: nested `chat_template_kwargs` replaces the entire top-level kwargs object.
- Fixed flags: `add_generation_prompt=true`, `continue_final_message=false`, `add_special_tokens=false`. Other values are rejected.
- The internal auto-parallel rendering flag is protocol-owned and cannot be set by the caller.

## Tools and history

Each function tool has `name`, optional `description`, an object `parameters`, and optional boolean/null `strict`. Function names use 1–64 ASCII letters/digits/underscores/dashes; tool names must be unique. Unknown tool/function fields are rejected.

The engine's ordered function representation is `name`, `description`, `parameters`, `strict`. Missing description/strict become null in that representation. Nested schema keys, arrays, `$defs`, `$ref`, `anyOf`, defaults and extension fields retain their content and order. No estimated tool overhead is added.

Historical assistant calls must have unique nonempty IDs and function names. Their `arguments` must be JSON **strings** that decode to objects, including `"{}"`. They are decoded exactly once in a private copy. Each call requires one subsequent matching tool-result message before the next turn. Parallel calls and successive tool rounds are supported; the supplied message order is retained.

Raw assistant text containing `<think>`/`</think>` is preserved in the tools profile and passed to the pinned serving template. The template may itself omit prior thinking before a later user turn, matching serving behavior. The local limit gate performs no additional truncation. Other protocol/control markup in message text is rejected. The old text-only profile still rejects reasoning markup.

## Serialization boundary

The renderer is MiniJinja 2.18.0 with the source-matched whitespace and Python-method compatibility settings. Its JSON filter preserves insertion order, emits Unicode directly and uses spaces after commas/colons. Direct scalar forms use serving spellings such as `none`, `true` and `false`.

Tool schemas and decoded arguments support JSON strings, null, booleans, signed 64-bit integers, arrays and objects. Floating-point values are refused because universal Python/serde_json float spelling parity is not qualified. In raw historical tool-argument strings, numeric `-0` is refused before decoding can discard its sign; this applies at any nesting depth. Ordinary integer `0`, negative integers and string `"-0"` are supported. This does not prohibit ordinary numeric `temperature`/`top_p` sampling controls, which are not rendered.

Direct entries in `parameters.properties` must be objects. If a direct property's `type` or `description` is present it must be a string; array-valued `type` is not qualified, while nested `anyOf` remains supported. Malformed JSON, duplicate keys, non-finite numbers, non-JSON Python values and unpaired Unicode surrogates are rejected.

## Non-rendering controls

Recognized controls: `max_tokens`, `max_completion_tokens`, `temperature`, `top_p`, `seed`, `n=1`, `stream`, `stream_options.include_usage`, `stop` (up to four strings), `presence_penalty`, `frequency_penalty`, `logprobs`, `top_logprobs`, `response_format`, `user`, `store`, `service_tier`. Basic shape/range checks do not replace endpoint validation.

`thinking_token_budget` may be null, -1, or a nonnegative signed 64-bit integer. It affects output sampling rather than input rendering. Unknown fields and unsupported extra kwargs are refused.

## Gate semantics

Admission requires a successful full count **and** `within_input_limit=true`. Default limit: 8,192 inclusive. Invalid inputs have no admission result; do not catch an error and send anyway. `--project-only` is not a gate. The counter does not perform HTTP requests, rewrite the original request, check output correctness, or enforce billing policy.

Use `serving_profile.load_json` on the raw serialized request when possible: a Python dictionary cannot reveal duplicate keys already discarded by another parser. Send the same unchanged content and object ordering that was counted; SDK/client transformations after counting require their own validation.

## Report privacy

CLI reports and `evaluate_request()` default to counts, the admission decision and public fingerprints, without request content, token IDs or local paths. `--include-details` / `include_details=True` includes sensitive request content and reversible token IDs. The lower-level `LocalCounter.count()` and projection helpers also return detailed data. Do not publish these detailed results or enable routine logging of them. `--project-only` requires `--include-details` and never produces an admission decision.
