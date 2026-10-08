"""Unit tests for the receptionist agent configuration."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent import (
    Assistant,
    CallLifecycle,
    _should_end_after_agent_state,
    _should_end_after_user_state,
    create_llm,
    create_stt,
    create_tts,
)


def test_speech_synthesis_uses_direct_deepgram(monkeypatch):
    tts_config = object()
    calls = []

    def fake_tts(**kwargs):
        calls.append(kwargs)
        return tts_config

    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setattr("agent.deepgram.TTS", fake_tts)

    assert create_tts() is tts_config
    assert calls == [{"model": "aura-2-arcas-en"}]


def test_speech_synthesis_requires_deepgram_api_key(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        create_tts()


def test_speech_recognition_uses_direct_deepgram(monkeypatch):
    stt_config = object()
    calls = []

    def fake_stt(**kwargs):
        calls.append(kwargs)
        return stt_config

    monkeypatch.setenv("DEEPGRAM_API_KEY", "test-key")
    monkeypatch.setattr("agent.deepgram.STT", fake_stt)

    assert create_stt() is stt_config
    assert calls == [{"model": "nova-3", "language": "en"}]


def test_speech_recognition_requires_deepgram_api_key(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        create_stt()


def test_language_model_uses_google_gemini_directly(monkeypatch):
    llm_config = object()
    calls = []

    def fake_llm(**kwargs):
        calls.append(kwargs)
        return llm_config

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setattr("agent.google.LLM", fake_llm)

    assert create_llm() is llm_config
    assert calls == [
        {
            "model": "gemini-3.1-flash-lite",
            "thinking_config": {"thinking_level": "minimal"},
        }
    ]


def test_language_model_requires_google_api_key(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        create_llm()


def test_assistant_preserves_existing_tools_and_call_ending(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assistant = Assistant()
    assert {tool.info.name for tool in assistant.tools} == {
        "end_call",
        "check_availability",
        "book_appointment_slot",
        "request_callback",
    }

    end_call_tool = next(
        tool for tool in assistant.tools if tool.info.name == "end_call"
    )

    assert "completed request" in end_call_tool.info.description
    assert (
        "after a successful booking or callback request"
        in assistant.instructions.lower()
    )
    assert "five seconds" in assistant.instructions.lower()
    assert "caller_explicitly_said_goodbye set to true" in assistant.instructions


def test_ending_call_waits_for_silence_after_closing():
    lifecycle = CallLifecycle(end_after_silence=True)

    assert _should_end_after_user_state(lifecycle, "away")
    assert lifecycle.end_after_silence


def test_speaking_during_closing_grace_cancels_call_ending():
    lifecycle = CallLifecycle(end_after_silence=True, end_after_response=True)

    assert not _should_end_after_user_state(lifecycle, "speaking")
    assert not lifecycle.end_after_silence
    assert not _should_end_after_agent_state(lifecycle, "listening")


def test_inactivity_does_not_end_call_unless_closing_was_requested():
    lifecycle = CallLifecycle()

    assert not _should_end_after_user_state(lifecycle, "away")


def test_goodbye_ends_immediately_after_final_response():
    lifecycle = CallLifecycle(end_after_response=True)

    assert _should_end_after_agent_state(lifecycle, "listening")
    assert lifecycle.shutdown_triggered


# Agent behavior is also covered by the simulations in scenarios.yaml, which run
# full conversations against the agent on LiveKit Cloud (see README.md). The
# evaluation below is kept as an example of the in-process testing framework
# (https://docs.livekit.io/agents/start/testing/) for turn-level checks that
# need a live LLM session.
#
# import textwrap
#
# import pytest
# from livekit.agents import AgentSession, inference, llm
#
# from agent import Assistant
#
#
# def _judge_llm() -> llm.LLM:
#     return inference.LLM(model="openai/gpt-4.1-mini")
#
#
# @pytest.mark.asyncio
# async def test_offers_assistance() -> None:
#     """Evaluation of the agent's friendly nature."""
#     async with (
#         _judge_llm() as judge_llm,
#         AgentSession() as session,
#     ):
#         await session.start(Assistant())
#
#         # Run an agent turn following the user's greeting
#         result = await session.run(user_input="Hello")
#
#         # Evaluate the agent's response for friendliness
#         await (
#             result.expect.next_event()
#             .is_message(role="assistant")
#             .judge(
#                 judge_llm,
#                 intent=textwrap.dedent(
#                     """\
#                     Greets the user in a friendly manner.
#
#                     Optional context that may or may not be included:
#                     - Offer of assistance with any request the user may have
#                     - Other small talk or chit chat is acceptable, so long as it is friendly and not too intrusive
#                     """
#                 ),
#             )
#         )
#
#         # Ensures there are no function calls or other unexpected events
#         result.expect.no_more_events()
