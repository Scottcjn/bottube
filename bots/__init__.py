# SPDX-License-Identifier: MIT
"""BoTTube debate bot framework."""

from bots.rap_battle import (  # noqa: F401
    BattlePipeline,
    BattleResult,
    BattleScript,
    BattleStatus,
    BattleTracker,
    BattleVerse,
    DEFAULT_PERSONAS,
    PipelineConfig,
    RapPersona,
    ScriptGenerator,
    create_llm_backend,
)
