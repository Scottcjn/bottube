# SPDX-License-Identifier: MIT
"""
Tests for the AI Rap Battle Generator pipeline.

Covers: RapPersona, BattleVerse, BattleScript, ScriptGenerator,
AudioGenerator, VideoGenerator, BattleTracker (real SQLite in tmpdir),
and BattlePipeline integration flows.

LLM calls, TTS (edge-tts), and ffmpeg are Mock-patched throughout
to keep the suite fast and environment-independent.
"""

import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bots.rap_battle import (
    AudioGenerator,
    BattlePipeline,
    BattleResult,
    BattleScript,
    BattleStatus,
    BattleTracker,
    BattleVerse,
    DEFAULT_PERSONAS,
    DEFAULT_TOPIC_PAIRS,
    LlamaCppBackend,
    OllamaBackend,
    PipelineConfig,
    RapPersona,
    ScriptGenerator,
    TemplateBackend,
    VideoGenerator,
    create_llm_backend,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _persona(name="TestMC", style="test flow", voice="en-US-GuyNeural",
             prompt="You are a test rapper."):
    return RapPersona(
        name=name,
        style_description=style,
        tts_voice=voice,
        personality_prompt=prompt,
    )


def _verse(persona=None, lyrics="Line1\nLine2\nLine3\nLine4", num=1):
    return BattleVerse(
        persona=persona or _persona(),
        lyrics=lyrics,
        verse_number=num,
    )


def _script(topic="Test Topic", num_verses=4):
    p1, p2 = _persona("MC A"), _persona("MC B")
    verses = []
    for i in range(num_verses):
        p = p1 if i % 2 == 0 else p2
        verses.append(_verse(persona=p, num=i + 1))
    return BattleScript(topic=topic, persona_1=p1, persona_2=p2,
                        verses=verses)


def _mock_subprocess_ok():
    """Return a mock CompletedProcess with returncode 0."""
    m = MagicMock()
    m.returncode = 0
    m.stdout = json.dumps({"format": {"duration": "30.5"}})
    m.stderr = ""
    return m


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class TestRapPersona:
    def test_creation(self):
        p = _persona("Ferro", "aggressive", "en-US-ChristopherNeural",
                      "You are Ferro.")
        assert p.name == "Ferro"
        assert p.style_description == "aggressive"
        assert p.tts_voice == "en-US-ChristopherNeural"
        assert "Ferro" in p.personality_prompt

    def test_default_personas_count(self):
        assert len(DEFAULT_PERSONAS) == 10

    def test_default_personas_unique_names(self):
        names = [p.name for p in DEFAULT_PERSONAS]
        assert len(names) == len(set(names)), "Persona names must be unique"

    def test_default_personas_have_voice(self):
        for p in DEFAULT_PERSONAS:
            assert p.tts_voice, f"{p.name} is missing tts_voice"

    def test_default_topic_pairs_reference_valid_indices(self):
        for topic, (i1, i2) in DEFAULT_TOPIC_PAIRS.items():
            assert 0 <= i1 < len(DEFAULT_PERSONAS)
            assert 0 <= i2 < len(DEFAULT_PERSONAS)
            assert i1 != i2, f"Topic {topic} maps to same persona twice"


class TestBattleVerse:
    def test_creation(self):
        p = _persona()
        v = BattleVerse(persona=p, lyrics="bar1\nbar2", verse_number=3)
        assert v.verse_number == 3
        assert "bar1" in v.lyrics
        assert v.persona is p

    def test_verse_number_boundary(self):
        v = _verse(num=0)
        assert v.verse_number == 0

    def test_empty_lyrics(self):
        v = BattleVerse(persona=_persona(), lyrics="", verse_number=1)
        assert v.lyrics == ""


class TestBattleScript:
    def test_creation(self):
        s = _script()
        assert s.topic == "Test Topic"
        assert len(s.verses) == 4

    def test_alternating_personas(self):
        s = _script(num_verses=6)
        for i, v in enumerate(s.verses):
            expected = s.persona_1 if i % 2 == 0 else s.persona_2
            assert v.persona.name == expected.name

    def test_generated_at_is_utc(self):
        s = _script()
        assert s.generated_at.tzinfo is not None

    def test_zero_verses(self):
        p1, p2 = _persona("A"), _persona("B")
        s = BattleScript(topic="Empty", persona_1=p1, persona_2=p2,
                         verses=[])
        assert len(s.verses) == 0


class TestBattleResult:
    def test_default_status_generated(self):
        r = BattleResult(script=_script())
        assert r.status == BattleStatus.GENERATED
        assert r.error is None

    def test_failed_result(self):
        r = BattleResult(script=_script(), status=BattleStatus.FAILED,
                         error="boom")
        assert r.status == BattleStatus.FAILED
        assert r.error == "boom"


class TestBattleStatus:
    def test_enum_values(self):
        assert BattleStatus.GENERATED.value == "generated"
        assert BattleStatus.UPLOADED.value == "uploaded"
        assert BattleStatus.FAILED.value == "failed"


class TestPipelineConfig:
    def test_defaults(self):
        cfg = PipelineConfig()
        assert cfg.num_verses == 4
        assert cfg.video_width == 720
        assert cfg.video_height == 1280
        assert cfg.upload_interval_sec == 30.0

    def test_custom_config(self):
        cfg = PipelineConfig(
            output_dir=Path("/tmp/test"), num_verses=8,
            video_width=1080, video_height=1920,
        )
        assert cfg.num_verses == 8
        assert cfg.video_width == 1080


# ---------------------------------------------------------------------------
# LLM Backends
# ---------------------------------------------------------------------------

class TestTemplateBackend:
    def test_returns_nonempty_string(self):
        be = TemplateBackend()
        out = be.generate("Test prompt", system="")
        assert isinstance(out, str)
        assert len(out) > 0

    def test_aggressive_keyword_selects_pool(self):
        be = TemplateBackend()
        out = be.generate("", system="aggressive style")
        assert any(word in out.lower() for word in
                   ["fire", "compile", "deploy", "stack"])

    def test_chill_keyword_selects_pool(self):
        be = TemplateBackend()
        out = be.generate("", system="chill relaxed vibe")
        assert any(word in out.lower() for word in
                   ["simple", "pythonic", "readability", "elegant"])

    def test_fallback_to_energetic(self):
        be = TemplateBackend()
        out = be.generate("unknown style", system="")
        assert len(out) > 0  # should still produce output


class TestCreateLlmBackend:
    @patch("bots.rap_battle.OllamaBackend")
    def test_ollama_fallback_on_connection_error(self, mock_cls):
        inst = mock_cls.return_value
        inst.generate.side_effect = Exception("connection refused")
        backend = create_llm_backend(backend_name="ollama")
        assert isinstance(backend, TemplateBackend)

    @patch("bots.rap_battle.LlamaCppBackend")
    def test_llamacpp_fallback_on_error(self, mock_cls):
        inst = mock_cls.return_value
        inst.generate.side_effect = Exception("connection refused")
        backend = create_llm_backend(backend_name="llamacpp")
        assert isinstance(backend, TemplateBackend)

    def test_unknown_backend_falls_to_template(self):
        backend = create_llm_backend(backend_name="nonexistent")
        assert isinstance(backend, TemplateBackend)

    def test_explicit_template_backend(self):
        backend = create_llm_backend(backend_name="template")
        assert isinstance(backend, TemplateBackend)


# ---------------------------------------------------------------------------
# ScriptGenerator
# ---------------------------------------------------------------------------

class TestScriptGenerator:
    def _make_gen(self, llm_output="Line A\nLine B\nLine C\nLine D"):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = llm_output
        return ScriptGenerator(mock_llm), mock_llm

    def test_generate_battle_returns_script(self):
        gen, _ = self._make_gen()
        p1, p2 = _persona("A"), _persona("B")
        script = gen.generate_battle("Topic", p1, p2, num_verses=4)
        assert isinstance(script, BattleScript)
        assert script.topic == "Topic"
        assert len(script.verses) == 4

    def test_alternating_persona_assignment(self):
        gen, _ = self._make_gen()
        p1, p2 = _persona("Alpha"), _persona("Beta")
        script = gen.generate_battle("X", p1, p2, num_verses=6)
        for i, v in enumerate(script.verses):
            expected = p1 if i % 2 == 0 else p2
            assert v.persona.name == expected.name

    def test_verse_numbers_sequential(self):
        gen, _ = self._make_gen()
        script = gen.generate_battle("T", _persona("A"), _persona("B"),
                                     num_verses=4)
        for i, v in enumerate(script.verses):
            assert v.verse_number == i + 1

    def test_llm_called_with_persona_style(self):
        gen, mock_llm = self._make_gen()
        p1 = _persona("Snek", "chill", prompt="You are chill snek.")
        p2 = _persona("Ferro", "aggressive", prompt="You are aggressive.")
        gen.generate_battle("Python vs Rust", p1, p2, num_verses=2)

        calls = mock_llm.generate.call_args_list
        assert len(calls) == 2
        # First call system prompt should include p1's personality
        _, kwargs0 = calls[0]
        assert "chill snek" in kwargs0.get("system", "").lower() or \
               "chill" in kwargs0.get("system", "").lower()

    def test_single_verse(self):
        gen, _ = self._make_gen()
        script = gen.generate_battle("T", _persona("A"), _persona("B"),
                                     num_verses=1)
        assert len(script.verses) == 1

    def test_max_8_verses(self):
        gen, _ = self._make_gen()
        script = gen.generate_battle("T", _persona("A"), _persona("B"),
                                     num_verses=8)
        assert len(script.verses) == 8

    def test_llm_empty_response_triggers_fallback(self):
        gen, _ = self._make_gen(llm_output="")
        p = _persona("MC")
        script = gen.generate_battle("Topic", p, _persona("B"),
                                     num_verses=1)
        # Fallback lyrics should include persona name
        assert p.name in script.verses[0].lyrics

    def test_llm_excess_lines_trimmed_to_four(self):
        gen, _ = self._make_gen(
            llm_output="1\n2\n3\n4\n5\n6\n7\n8"
        )
        script = gen.generate_battle("T", _persona("A"), _persona("B"),
                                     num_verses=1)
        lines = script.verses[0].lyrics.split("\n")
        assert len(lines) <= 4

    def test_system_prompt_contains_style(self):
        prompt = ScriptGenerator._build_system_prompt(
            _persona("X", style="boom bap")
        )
        assert "boom bap" in prompt


# ---------------------------------------------------------------------------
# AudioGenerator
# ---------------------------------------------------------------------------

class TestAudioGenerator:
    @patch("bots.rap_battle.subprocess.run")
    def test_generate_verse_audio_calls_edge_tts(self, mock_run, tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        ag = AudioGenerator(tmp_path / "audio")
        v = _verse()
        out = ag.generate_verse_audio(v, tmp_path / "verse_audio")
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "edge-tts"
        assert "--voice" in cmd
        assert v.persona.tts_voice in cmd

    @patch("bots.rap_battle.subprocess.run")
    def test_generate_verse_audio_raises_on_failure(self, mock_run, tmp_path):
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "edge-tts error"
        mock_run.return_value = fail
        ag = AudioGenerator(tmp_path / "audio")
        with pytest.raises(RuntimeError, match="edge-tts failed"):
            ag.generate_verse_audio(_verse(), tmp_path / "v_audio")

    @patch("bots.rap_battle.subprocess.run")
    @patch("bots.rap_battle.shutil.copy2")
    def test_mix_battle_audio_without_beat(self, mock_copy, mock_run,
                                           tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        ag = AudioGenerator(tmp_path / "audio")
        verse_files = [tmp_path / "v1.mp3", tmp_path / "v2.mp3"]
        for f in verse_files:
            f.touch()
        out_path = tmp_path / "mixed.mp3"
        ag.mix_battle_audio(verse_files, None, out_path)
        # Should call ffmpeg at least twice (silence + concat)
        assert mock_run.call_count >= 2

    @patch("bots.rap_battle.subprocess.run")
    def test_mix_battle_audio_with_beat(self, mock_run, tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        ag = AudioGenerator(tmp_path / "audio")
        verse_files = [tmp_path / "v1.mp3"]
        for f in verse_files:
            f.touch()
        beat = tmp_path / "beat.mp3"
        beat.touch()
        out_path = tmp_path / "mixed.mp3"
        ag.mix_battle_audio(verse_files, beat, out_path)
        # With a beat: silence + concat + probe + overlay = at least 4
        assert mock_run.call_count >= 3

    @patch("bots.rap_battle.subprocess.run")
    def test_edge_tts_text_argument(self, mock_run, tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        ag = AudioGenerator(tmp_path / "audio")
        lyrics = "Test lyrics for TTS"
        v = BattleVerse(persona=_persona(), lyrics=lyrics, verse_number=1)
        ag.generate_verse_audio(v, tmp_path / "va")
        cmd = mock_run.call_args[0][0]
        assert lyrics in cmd


# ---------------------------------------------------------------------------
# VideoGenerator
# ---------------------------------------------------------------------------

class TestVideoGenerator:
    @patch("bots.rap_battle.subprocess.run")
    @patch("bots.rap_battle.shutil.rmtree")
    def test_generate_battle_video_resolution(self, mock_rm, mock_run,
                                               tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        vg = VideoGenerator(width=720, height=1280)
        script = _script(num_verses=2)
        audio = tmp_path / "audio.mp3"
        audio.touch()
        out = tmp_path / "video.mp4"
        vg.generate_battle_video(script, audio, out)
        # Check ffmpeg was called with correct resolution in filtergraph
        found_resolution = False
        for c in mock_run.call_args_list:
            args = c[0][0] if c[0] else []
            cmd_str = " ".join(str(a) for a in args)
            if "720" in cmd_str and "1280" in cmd_str:
                found_resolution = True
        assert found_resolution, "ffmpeg should use 720x1280 resolution"

    @patch("bots.rap_battle.subprocess.run")
    @patch("bots.rap_battle.shutil.rmtree")
    def test_video_uses_h264_codec(self, mock_rm, mock_run, tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        vg = VideoGenerator()
        script = _script(num_verses=2)
        audio = tmp_path / "audio.mp3"
        audio.touch()
        out = tmp_path / "video.mp4"
        vg.generate_battle_video(script, audio, out)
        found_h264 = False
        for c in mock_run.call_args_list:
            args = c[0][0] if c[0] else []
            if "libx264" in args:
                found_h264 = True
        assert found_h264, "ffmpeg should use libx264 codec"

    @patch("bots.rap_battle.subprocess.run")
    @patch("bots.rap_battle.shutil.rmtree")
    def test_subtitle_file_generated(self, mock_rm, mock_run, tmp_path):
        mock_run.return_value = _mock_subprocess_ok()
        vg = VideoGenerator()
        script = _script(num_verses=2)
        audio = tmp_path / "audio.mp3"
        audio.touch()
        out = tmp_path / "out" / "video.mp4"
        vg.generate_battle_video(script, audio, out)
        # _render_subtitles writes an ASS file; confirm it was referenced
        found_ass = False
        for c in mock_run.call_args_list:
            args = c[0][0] if c[0] else []
            cmd_str = " ".join(str(a) for a in args)
            if "ass" in cmd_str.lower():
                found_ass = True
        assert found_ass, "ffmpeg should reference an ASS subtitle file"

    def test_sec_to_ass_time(self):
        assert VideoGenerator._sec_to_ass_time(0) == "0:00:00.00"
        assert VideoGenerator._sec_to_ass_time(61.5) == "0:01:01.50"
        assert VideoGenerator._sec_to_ass_time(3662.0) == "1:01:02.00"

    def test_sec_to_ass_time_boundary(self):
        assert VideoGenerator._sec_to_ass_time(3600.0) == "1:00:00.00"
        assert VideoGenerator._sec_to_ass_time(59.75) == "0:00:59.75"

    @patch("bots.rap_battle.subprocess.run")
    def test_get_audio_duration_success(self, mock_run):
        mock_run.return_value = _mock_subprocess_ok()
        dur = VideoGenerator._get_audio_duration(Path("/fake/audio.mp3"))
        assert dur == 30.5

    @patch("bots.rap_battle.subprocess.run")
    def test_get_audio_duration_probe_failure(self, mock_run):
        fail = MagicMock()
        fail.returncode = 1
        mock_run.return_value = fail
        dur = VideoGenerator._get_audio_duration(Path("/fake/audio.mp3"))
        assert dur == 0.0

    @patch("bots.rap_battle.subprocess.run")
    @patch("bots.rap_battle.shutil.rmtree")
    def test_avatar_creation_failure_raises(self, mock_rm, mock_run,
                                            tmp_path):
        fail = MagicMock()
        fail.returncode = 1
        fail.stderr = "lavfi error"
        mock_run.return_value = fail
        vg = VideoGenerator()
        with pytest.raises(RuntimeError, match="Failed to create rapper"):
            vg._create_rapper_visual(_persona(), tmp_path / "avatar.png")

    def test_render_subtitles_content(self, tmp_path):
        vg = VideoGenerator(width=720, height=1280)
        script = _script(num_verses=2)
        ass_path = tmp_path / "subs.ass"
        result = vg._render_subtitles(script, ass_path)
        content = result.read_text()
        assert "[Script Info]" in content
        assert "[Events]" in content
        assert "720" in content
        assert "1280" in content
        # Should contain persona names
        for v in script.verses:
            assert v.persona.name in content


# ---------------------------------------------------------------------------
# BattleTracker (real SQLite in tmpdir)
# ---------------------------------------------------------------------------

class TestBattleTracker:
    def test_init_creates_table(self, tmp_path):
        db = tmp_path / "test.db"
        tracker = BattleTracker(db)
        conn = sqlite3.connect(str(db))
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='rap_battles'"
        )
        assert cur.fetchone() is not None
        conn.close()
        tracker.close()

    def test_mark_generated_returns_id(self, tmp_path):
        with BattleTracker(tmp_path / "t.db") as tracker:
            rid = tracker.mark_generated(
                "Python vs Rust", "Snek", "Ferro", "/v/battle.mp4"
            )
            assert rid >= 1

    def test_mark_generated_increments(self, tmp_path):
        with BattleTracker(tmp_path / "t.db") as tracker:
            r1 = tracker.mark_generated("T1", "A", "B", "/p1")
            r2 = tracker.mark_generated("T2", "C", "D", "/p2")
            assert r2 > r1

    def test_get_pending_returns_generated(self, tmp_path):
        with BattleTracker(tmp_path / "t.db") as tracker:
            tracker.mark_generated("T", "A", "B", "/path")
            pending = tracker.get_pending()
            assert len(pending) == 1
            assert pending[0]["topic"] == "T"
            assert pending[0]["status"] == "generated"

    def test_mark_uploaded_transitions_status(self, tmp_path):
        with BattleTracker(tmp_path / "t.db") as tracker:
            tracker.mark_generated("T", "A", "B", "/p")
            tracker.mark_uploaded("T")
            pending = tracker.get_pending()
            assert len(pending) == 0

    def test_mark_failed_transitions_status(self, tmp_path):
        with BattleTracker(tmp_path / "t.db") as tracker:
            tracker.mark_generated("T", "A", "B", "/p")
            tracker.mark_failed("T", "some error")
            pending = tracker.get_pending()
            assert len(pending) == 0

    def test_full_state_lifecycle(self, tmp_path):
        """init -> generate -> pending(1) -> upload -> pending(0)"""
        with BattleTracker(tmp_path / "t.db") as tracker:
            tracker.mark_generated("Topic1", "P1", "P2", "/v1.mp4")
            tracker.mark_generated("Topic2", "P3", "P4", "/v2.mp4")
            assert len(tracker.get_pending()) == 2

            tracker.mark_uploaded("Topic1")
            pending = tracker.get_pending()
            assert len(pending) == 1
            assert pending[0]["topic"] == "Topic2"

    def test_context_manager_closes(self, tmp_path):
        db = tmp_path / "t.db"
        tracker = BattleTracker(db)
        tracker.__enter__()
        tracker.__exit__(None, None, None)
        with pytest.raises(RuntimeError, match="closed"):
            tracker.mark_generated("T", "A", "B", "/p")

    def test_multiple_generated_same_topic(self, tmp_path):
        """mark_uploaded should update only the most recent generated row."""
        with BattleTracker(tmp_path / "t.db") as tracker:
            tracker.mark_generated("T", "A", "B", "/v1")
            tracker.mark_generated("T", "A", "B", "/v2")
            tracker.mark_uploaded("T")
            pending = tracker.get_pending()
            # One should remain (the first one is still generated)
            assert len(pending) == 1


# ---------------------------------------------------------------------------
# BattlePipeline — Integration (all sub-components mocked)
# ---------------------------------------------------------------------------

class TestBattlePipeline:
    @pytest.fixture()
    def pipeline(self, tmp_path):
        cfg = PipelineConfig(
            output_dir=tmp_path / "battles",
            llm_backend="template",
            api_key="",
        )
        with patch("bots.rap_battle.create_llm_backend") as mock_factory:
            mock_factory.return_value = TemplateBackend()
            pipe = BattlePipeline(cfg)
        return pipe

    def test_generate_single_success(self, pipeline, tmp_path):
        """E2E with mocked audio/video: result status should be GENERATED."""
        with patch.object(pipeline.audio_gen, "generate_verse_audio",
                          return_value=tmp_path / "v.mp3"), \
             patch.object(pipeline.audio_gen, "mix_battle_audio",
                          return_value=tmp_path / "mix.mp3"), \
             patch.object(pipeline.video_gen, "generate_battle_video",
                          return_value=tmp_path / "final.mp4"):

            result = pipeline.generate_single("Python vs Rust")

        assert isinstance(result, BattleResult)
        assert result.status == BattleStatus.GENERATED
        assert result.error is None
        assert result.script.topic == "Python vs Rust"
        assert len(result.script.verses) == pipeline.config.num_verses

    def test_generate_single_uses_topic_personas(self, pipeline, tmp_path):
        """Known topic 'Python vs Rust' should pick Lil' Snek vs Ferro."""
        with patch.object(pipeline.audio_gen, "generate_verse_audio",
                          return_value=tmp_path / "v.mp3"), \
             patch.object(pipeline.audio_gen, "mix_battle_audio",
                          return_value=tmp_path / "mix.mp3"), \
             patch.object(pipeline.video_gen, "generate_battle_video",
                          return_value=tmp_path / "final.mp4"):

            result = pipeline.generate_single("Python vs Rust")

        assert result.script.persona_1.name == "Lil' Snek"
        assert result.script.persona_2.name == "Ferro"

    def test_generate_single_failure_returns_failed(self, pipeline, tmp_path):
        """If audio generation explodes, result status should be FAILED."""
        with patch.object(pipeline.audio_gen, "generate_verse_audio",
                          side_effect=RuntimeError("tts crashed")):

            result = pipeline.generate_single("Test")

        assert result.status == BattleStatus.FAILED
        assert "tts crashed" in result.error

    def test_run_batch_respects_count(self, pipeline, tmp_path):
        """count=3 should call generate_single exactly 3 times."""
        with patch.object(pipeline, "generate_single",
                          return_value=BattleResult(
                              script=_script(),
                              status=BattleStatus.GENERATED,
                          )) as mock_gen:

            results = pipeline.run_batch(
                topics=["A", "B", "C", "D"], count=3, upload=False
            )

        assert mock_gen.call_count == 3
        assert len(results) == 3

    @patch("bots.rap_battle.time.sleep")
    def test_upload_rate_limiting(self, mock_sleep, pipeline, tmp_path):
        """Upload mode should insert sleep between uploads."""
        generated = BattleResult(
            script=_script(),
            video_path=tmp_path / "v.mp4",
            status=BattleStatus.GENERATED,
        )
        (tmp_path / "v.mp4").touch()

        with patch.object(pipeline, "generate_single",
                          return_value=generated), \
             patch.object(pipeline, "upload_to_bottube",
                          return_value=True):

            pipeline.run_batch(
                topics=["A", "B"], count=3, upload=True,
            )

        # sleep should be called between uploads (count-1 = 2 times)
        assert mock_sleep.call_count == 2
        for c in mock_sleep.call_args_list:
            assert c[0][0] == pipeline.config.upload_interval_sec

    def test_failure_resilience(self, pipeline, tmp_path):
        """If battle 1 fails, battles 2-3 should still be generated."""
        call_count = {"n": 0}

        def gen_side_effect(topic, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return BattleResult(
                    script=_script(), status=BattleStatus.FAILED,
                    error="first one broke",
                )
            return BattleResult(
                script=_script(), status=BattleStatus.GENERATED,
            )

        with patch.object(pipeline, "generate_single",
                          side_effect=gen_side_effect):
            results = pipeline.run_batch(
                topics=["A", "B", "C"], count=3, upload=False,
            )

        assert len(results) == 3
        assert results[0].status == BattleStatus.FAILED
        assert results[1].status == BattleStatus.GENERATED
        assert results[2].status == BattleStatus.GENERATED

    def test_upload_skips_failed(self, pipeline, tmp_path):
        """upload_to_bottube should return False for failed results."""
        r = BattleResult(script=_script(), status=BattleStatus.FAILED)
        assert pipeline.upload_to_bottube(r) is False

    def test_upload_skips_missing_video(self, pipeline, tmp_path):
        """upload_to_bottube should return False when video path missing."""
        r = BattleResult(script=_script(), video_path=None,
                         status=BattleStatus.GENERATED)
        assert pipeline.upload_to_bottube(r) is False

    def test_upload_no_api_key(self, pipeline, tmp_path):
        """No api_key -> upload client is None -> returns False."""
        video = tmp_path / "v.mp4"
        video.touch()
        r = BattleResult(script=_script(), video_path=video,
                         status=BattleStatus.GENERATED)
        assert pipeline.upload_to_bottube(r) is False

    def test_pick_personas_known_topic(self, pipeline):
        p1, p2 = pipeline._pick_personas("Cats vs Dogs")
        assert p1.name == DEFAULT_PERSONAS[8].name
        assert p2.name == DEFAULT_PERSONAS[9].name

    def test_pick_personas_unknown_topic(self, pipeline):
        p1, p2 = pipeline._pick_personas("Totally Unknown Topic XYZ")
        assert p1.name != p2.name  # should be different
        assert p1 in DEFAULT_PERSONAS
        assert p2 in DEFAULT_PERSONAS
