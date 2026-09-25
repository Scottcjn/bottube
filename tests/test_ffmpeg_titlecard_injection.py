# SPDX-License-Identifier: MIT
"""Regression: the title-card prompt must never reach a shell.

FFmpegTitleCardProvider.submit used to interpolate the user prompt into a
``shell=True`` command, escaping only ``'`` and ``:``, so ``$(...)`` and
backticks in a prompt executed on the host.
"""

import os
import subprocess

from generation.models import GenerationRequest
from generation.providers import ffmpeg_titlecard
from generation.providers.ffmpeg_titlecard import FFmpegTitleCardProvider


def test_shell_metacharacters_in_prompt_are_not_executed(tmp_path, monkeypatch):
    pwned = tmp_path / "pwned"
    backtick = tmp_path / "pwned_backtick"
    prompt = "hi $(touch pwned) `touch pwned_backtick` it's 10:30 100%"
    monkeypatch.chdir(tmp_path)  # relative targets keep textwrap from splitting them

    # Stand-in "ffmpeg" that ignores its arguments, run through the real
    # subprocess.run so any shell expansion would actually happen.
    monkeypatch.setattr(ffmpeg_titlecard, "FFMPEG", "true")
    calls = []
    real_run = subprocess.run

    def spy_run(cmd, *args, **kwargs):
        calls.append((cmd, kwargs))
        textfile = next(a for a in cmd if "textfile=" in a) if isinstance(cmd, list) else None
        if textfile:
            name = textfile.split("textfile='", 1)[1].split("'", 1)[0]
            with open(os.path.join(kwargs["cwd"], name), encoding="utf-8") as fh:
                calls[-1] += (fh.read(),)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(ffmpeg_titlecard.subprocess, "run", spy_run)

    ok, msg = FFmpegTitleCardProvider().submit(GenerationRequest(prompt=prompt), tmp_path / "out")

    assert not pwned.exists()
    assert not backtick.exists()
    assert ok is False and "empty output" in msg  # "true" writes no video

    (cmd, kwargs, text), = calls
    assert isinstance(cmd, list)
    assert not kwargs.get("shell")
    assert all("$(" not in arg and "`" not in arg for arg in cmd)
    # The prompt is handed to drawtext verbatim via textfile=.
    assert " ".join(text.split()) == prompt
    # The temporary text file is cleaned up.
    assert list((tmp_path / "out").glob("*.txt")) == []
