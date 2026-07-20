"""Compose the five prompt layers in one auditable, deterministic order."""

from dataclasses import dataclass

from anime_assistant.ai.prompts.behavior import (
    build_behavior_layer,
    derive_behavior_state,
)
from anime_assistant.ai.prompts.context import build_context_layer
from anime_assistant.ai.prompts.identity import build_identity_layer
from anime_assistant.ai.prompts.output_rules import build_output_rules_layer
from anime_assistant.ai.prompts.values import build_values_layer


PROMPT_LAYER_ORDER = ("identity", "values", "behavior", "context", "output_rules")
ALLOWED_PROMPT_MODES = {"chat", "greeting", "proactive"}


@dataclass(frozen=True)
class PromptLayers:
    identity: str
    values: str
    behavior: str
    context: str
    output_rules: str

    def render(self):
        return "\n\n".join(getattr(self, name).strip() for name in PROMPT_LAYER_ORDER)


def build_prompt_layers(
    context,
    persona,
    memory_context=None,
    mode="chat",
    include_emotion_control=True,
    purpose_hint=None,
):
    if mode not in ALLOWED_PROMPT_MODES:
        raise ValueError(f"Unsupported prompt mode: {mode}")
    if mode != "chat":
        include_emotion_control = False
    behavior_state = derive_behavior_state(context, mode=mode)
    return PromptLayers(
        identity=build_identity_layer(persona),
        values=build_values_layer(),
        behavior=build_behavior_layer(context, mode=mode),
        context=build_context_layer(
            context,
            memory_context or {},
            behavior_state,
            mode=mode,
            purpose_hint=purpose_hint,
        ),
        output_rules=build_output_rules_layer(
            mode=mode,
            include_emotion_control=include_emotion_control,
        ),
    )


def build_five_layer_prompt(*args, **kwargs):
    return build_prompt_layers(*args, **kwargs).render()
