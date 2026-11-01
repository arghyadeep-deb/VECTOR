"""
LLM-based follow-up question generator.

Uses the model to reformulate follow-up questions based on prior research context,
producing more targeted search queries than simple concatenation.
"""

from typing import Dict, List
from loguru import logger
from .base_followup_question import BaseFollowUpQuestionGenerator


class LLMFollowUpQuestionGenerator(BaseFollowUpQuestionGenerator):
    """LLM-based follow-up question generator."""

    def generate_contextualized_query(
        self,
        follow_up_query: str,
        original_query: str,
        past_findings: str,
        **kwargs,
    ) -> str:
        """Generate a contextualized query using LLM reformulation."""
        prompt = (
            f"You are a research assistant helping refine a follow-up search query.\n\n"
            f"Original research question: {original_query}\n\n"
            f"What has already been found:\n{past_findings[:2000]}\n\n"
            f"Follow-up question from the user: {follow_up_query}\n\n"
            "Based on the above, write a single, focused internet search query that fills "
            "the most important remaining information gap. Output ONLY the search query text, "
            "nothing else."
        )
        try:
            response = self.model.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            # Strip chain-of-thought think tags if present
            if "<think>" in content and "</think>" in content:
                content = content.split("</think>", 1)[-1]
            result = content.strip()
            if result:
                return result
        except Exception as e:
            logger.warning(
                f"LLM follow-up reformulation failed ({e}), falling back to simple concat"
            )
        # Graceful fallback
        from .simple_followup_question import SimpleFollowUpQuestionGenerator
        return SimpleFollowUpQuestionGenerator(self.model).generate_contextualized_query(
            follow_up_query, original_query, past_findings, **kwargs
        )

    def generate_questions(
        self,
        current_knowledge: str,
        query: str,
        questions_per_iteration: int,
        questions_by_iteration: Dict[int, List[str]],
    ) -> List[str]:
        """Generate multiple targeted follow-up questions using the LLM."""
        all_previous = [q for qs in questions_by_iteration.values() for q in qs]
        prev_block = "\n".join(f"- {q}" for q in all_previous[-10:]) if all_previous else "None"
        prompt = (
            f"You are a research assistant generating follow-up search questions.\n\n"
            f"Research query: {query}\n\n"
            f"Current knowledge summary:\n{current_knowledge[:2000]}\n\n"
            f"Questions already asked:\n{prev_block}\n\n"
            f"Generate exactly {questions_per_iteration} new, specific internet search "
            "questions that address remaining gaps. Do NOT repeat questions already asked.\n"
            "Format: one question per line, prefixed with 'Q: '."
        )
        try:
            response = self.model.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            if "<think>" in content and "</think>" in content:
                content = content.split("</think>", 1)[-1]
            questions = []
            for line in content.strip().splitlines():
                line = line.strip()
                if line.startswith("Q:"):
                    q = line[2:].strip()
                    if q:
                        questions.append(q)
            if questions:
                return questions[:questions_per_iteration]
        except Exception as e:
            logger.warning(
                f"LLM generate_questions failed ({e}), falling back to super()"
            )
        return super().generate_questions(
            current_knowledge,
            query,
            questions_per_iteration,
            questions_by_iteration,
        )
