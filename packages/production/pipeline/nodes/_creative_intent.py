"""Shared read helper for the CreativeIntentArtifact.

Every downstream consumer (StylePlanning today; ExportFinishedVideo once the cover
slice lands) reads creative_intent through this one helper so the None-artifact and
legacy-payload fallbacks live in a single place.

The read is **tolerant**: a run that was started before the field architecture
changed has a creative_intent payload carrying now-removed keys (scene_type, density,
...). Because ContractModel is ``extra="forbid"`` a naive ``model_validate`` would
raise on those, so we filter to the currently-declared fields first and fall back to
the stable ``intent`` blob if anything still fails to validate. This replaces a
node_version bump (node_version is a single global "v1"; bumping it would force every
resumed run to fully re-run) with a cheap, local migration that keeps old runs working.
"""

from __future__ import annotations

from pydantic import ValidationError

from packages.core.contracts import ArtifactKind
from packages.core.contracts.artifacts import CreativeIntentArtifact


def load_creative_intent(state) -> CreativeIntentArtifact:
    art = state.artifacts.get(ArtifactKind.creative_intent)
    if art is None:
        return CreativeIntentArtifact()
    payload = art.payload if isinstance(art.payload, dict) else {}
    known = {key: payload[key] for key in CreativeIntentArtifact.model_fields if key in payload}
    try:
        return CreativeIntentArtifact.model_validate(known)
    except ValidationError:
        intent = payload.get("intent")
        return CreativeIntentArtifact(intent=intent if isinstance(intent, dict) else None)
