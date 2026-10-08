"""Unit tests for the receptionist agent configuration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from agent import (
    Assistant,
    CallLifecycle,
    _should_end_after_agent_state,
    _should_end_after_user_state,
)


def test_assistant_registers_end_call_tool_with_listening_grace_period():
    assistant = Assistant()
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
