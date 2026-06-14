from __future__ import annotations

import json

from fastapi import Request

from apps.api.common import get_case, repository
from packages.ai.gateway import ProviderCall
from packages.ai.prompts.registry import case_prompt_variables
from packages.core import contracts as c
from packages.core.workflow import NodeExecutionError

# The merged/legacy prompt that every persona×operation variant falls back to when
# no published binding exists for the variant node (or that binding's content cannot
# be rendered against the variables we have). Keeps generation alive ("保证不挂").
_FALLBACK_SCRIPT_NODE_ID = "CaseAgentScriptGenerate"

# Prompt-resolution failures that should trigger the fallback instead of bubbling up:
# - version_not_published: no binding (or no published version) for the variant node.
# - render_error: a binding exists but its real-prompt content references tokens we do
#   not supply (e.g. {{variation_count}}, {{user_input}}, or embedded JSON braces), so
#   the variant template is incompatible with this call site -> degrade to the merged one.
_FALLBACK_ERROR_CODES = frozenset(
    {c.ErrorCode.prompt_version_not_published, c.ErrorCode.prompt_render_error}
)


def generate_script_with_llm(
    case_id: str,
    brief: str,
    memory_ids: list[str],
    memories: list[str],
    request: Request,
    persona_mode: str = "hard_ad",
    operation: str = "generate",
) -> str | None:
    profile = _select_real_llm_profile(request)
    if profile is None:
        return None
    # #B prompt wiring: fill the case profile vocabulary ({case_name}{product_name}
    # {industry}{target_audience}{ip_persona}{brand_voice}{key_selling_points}
    # {description}{tags}) so downstream templates no longer get permanent empties.
    # render() only substitutes tokens the template references, so these extras are
    # harmless for templates (like CaseAgentScriptGenerate) that ignore them.
    variables: dict[str, object] = {
        "brief": brief,
        "memories": " / ".join(memories) if memories else "暂无",
        "persona_mode": persona_mode,
        "operation": operation,
    }
    variables.update(case_prompt_variables(get_case(request, case_id)))
    # Route to the persona×operation variant node first; fall back to the merged
    # CaseAgentScriptGenerate prompt when the variant has no published binding or its
    # content cannot be rendered against these variables.
    variant_node_id = f"{_FALLBACK_SCRIPT_NODE_ID}.{persona_mode}.{operation}"
    prompt_invocation, rendered = _render_with_fallback(
        request,
        variant_node_id=variant_node_id,
        variables=variables,
        case_id=case_id,
        provider_profile_id=profile.id,
    )
    invocation, result = request.app.state.provider_gateway.invoke(
        ProviderCall(
            case_id=case_id,
            provider_profile_id=profile.id,
            capability_id="llm.chat",
            prompt_version_id=prompt_invocation.prompt_version_id,
            input={"prompt": rendered, "brief": brief, "memory_ids": memory_ids, "memories": memories},
        )
    )
    if result is None or invocation.error:
        raise NodeExecutionError(
            invocation.error.code if invocation.error else c.ErrorCode.provider_remote_failed,
            invocation.error.message if invocation.error else "Case agent LLM provider failed.",
        )
    repository(request).prompt_invocations[prompt_invocation.id] = prompt_invocation.model_copy(
        update={"provider_invocation_id": invocation.id, "updated_at": c.utcnow()}
    )
    script = _script_from_llm_output(result.output)
    if not script:
        raise NodeExecutionError(c.ErrorCode.provider_remote_failed, "Case agent LLM output missing script.")
    return script


def _render_with_fallback(
    request: Request,
    *,
    variant_node_id: str,
    variables: dict[str, object],
    case_id: str,
    provider_profile_id: str,
):
    """Render the variant prompt node, degrading to the merged node when it is
    unavailable or incompatible.

    The fallback covers two distinct failures (see ``_FALLBACK_ERROR_CODES``): the
    variant node has no published binding yet, or the bound (real, migrated) prompt
    references tokens this call site does not provide. In both cases we re-render
    against ``CaseAgentScriptGenerate`` so script generation never hard-fails on a
    missing/incompatible variant. Any other error (e.g. provider/output issues) is
    re-raised unchanged.
    """
    registry = request.app.state.prompt_registry
    try:
        return registry.render(
            node_id=variant_node_id,
            variables=variables,
            case_id=case_id,
            provider_profile_id=provider_profile_id,
        )
    except NodeExecutionError as exc:
        if exc.error.code not in _FALLBACK_ERROR_CODES:
            raise
    return registry.render(
        node_id=_FALLBACK_SCRIPT_NODE_ID,
        variables=variables,
        case_id=case_id,
        provider_profile_id=provider_profile_id,
    )


def _select_real_llm_profile(request: Request) -> c.ProviderProfile | None:
    gateway = request.app.state.provider_gateway
    for profile in repository(request).provider_profiles.values():
        if profile.capability != "llm.chat" or not profile.enabled or profile.provider_id == "sandbox":
            continue
        if profile.provider_id not in gateway.plugins:
            continue
        if profile.secret_ref and not gateway._secret_is_active(profile.secret_ref):
            continue
        return profile
    return None


def _script_from_llm_output(output: dict) -> str:
    for key in ("script", "draft", "polished_script", "content"):
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            if key == "content":
                parsed = _json_object(value)
                for nested_key in ("script", "draft", "polished_script"):
                    nested = parsed.get(nested_key)
                    if isinstance(nested, str) and nested.strip():
                        return nested.strip()
            return value.strip()
    return ""


def _json_object(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
