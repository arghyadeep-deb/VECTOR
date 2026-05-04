import asyncio
from dataclasses import asdict

from dotenv import load_dotenv

from .utils import load_instructions

load_dotenv("karpathy/.env")

COMMON_INSTRUCTIONS = load_instructions("common_instructions")


async def delegate_task(
    prompt: str,
    append_system_prompt: str,
):
    """Delegate a task to an expert

    Args:
        prompt: The prompt describing the task to delegate
        append_system_prompt: The system prompt describing the expert
    Returns:
        The result of the delegation with todos tracking and progress updates
    """
    # Import here to avoid Pydantic schema generation issues at module load time
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        ToolUseBlock,
        query,
    )

    result = None
    query_gen = query(
        prompt=f"{COMMON_INSTRUCTIONS}\n\nUser Prompt: {prompt}",
        options=ClaudeAgentOptions(
            system_prompt={
                "type": "preset",
                "preset": "claude_code",
                "append": append_system_prompt,
            },  # Use the preset
            setting_sources=["user", "project"],
            cwd="sandbox",
            permission_mode="bypassPermissions",
        ),
    )

    try:
        async for message in query_gen:
            # Print tool use blocks
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        if block.name == "Skill":
                            print(
                                f"Using the skill: {block.input.get('skill', 'unknown')}"
                            )
                        else:
                            print(f"Using the tool: {block.name}")

            # Check for ResultMessage and return the result
            elif isinstance(message, ResultMessage):
                result = asdict(message)
    finally:
        # Explicitly close the async generator
        await query_gen.aclose()

    return result


if __name__ == "__main__":
    # result = asyncio.run(conduct_research("What is the capital of France?"))
    # print(result)
    result = asyncio.run(
        delegate_task(
            "What Skills are available?",
            "You are a helpful assistant",
        )
    )
    print(result)
