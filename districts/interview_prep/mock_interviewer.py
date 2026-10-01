import sys
import uuid
import asyncio as _asyncio
import concurrent.futures as _cf
from typing import Optional

from loguru import logger
from core.config import CONFIG
from core.city.agent_base import AgentBase


def _llm(prompt: str, max_tokens: int = 800, temperature: float = 0.6) -> str:
    from core.inference.provider_client import ProviderClient as _PC
    async def _call():
        r = await _PC().chat(
            messages=[{"role": "user", "content": prompt}],
            tier="reasoning", temperature=temperature, max_tokens=max_tokens,
            caller_id="mock_interviewer",
        )
        return r.content
    with _cf.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_asyncio.run, _call()).result(timeout=90)


class MockInterviewer(AgentBase):
    """
    Conducts mock interviews with role-specific questions
    and provides evaluation feedback.
    """

    DIFFICULTY_LEVELS = ["easy", "medium", "hard", "expert"]
    QUESTION_TYPES = [
        "behavioral", "technical", "situational", "brain_teaser",
        "system_design", "coding", "communication", "leadership"
    ]

    def __init__(self, ghost: dict | None = None):
        super().__init__(str(uuid.uuid4()), "MockInterviewer", "interview_prep")
        self.capabilities = ["interview", "mock_interview"]
        if ghost:
            self.inherit_ghost(ghost)

        self._active_interviews: dict[str, dict] = {}
        self._question_history: list[dict] = []
        self._evaluation_cache: list[dict] = []
        logger.info("[VECTOR][mock_interviewer] MockInterviewer initialized")

    def start_interview(self, role: str, difficulty: str = "medium") -> dict:
        """
        Start a new mock interview session.
        Returns interview ID and initial question.
        """
        if difficulty not in self.DIFFICULTY_LEVELS:
            difficulty = "medium"

        interview_id = str(uuid.uuid4())

        interview = {
            "id": interview_id,
            "role": role,
            "difficulty": difficulty,
            "status": "active",
            "questions": [],
            "answers": [],
            "started_at": self._get_timestamp(),
            "current_question": 0,
            "total_questions": 5,
            "score": 0,
            "feedback": []
        }

        self._active_interviews[interview_id] = interview

        first_question = self.generate_question(role, difficulty, "behavioral")
        if "error" in first_question:
            # Don't leave a half-started session behind or report it as started.
            del self._active_interviews[interview_id]
            return {"status": "error", "error": first_question["error"], "role": role}
        # Record Q1 so get_next_question() doesn't re-ask question #1 and
        # end_interview() scores it.
        interview["questions"].append(first_question)
        interview["current_question"] = 1

        self.award_points(10, f"interview_started_{role}")
        logger.info(f"[VECTOR][mock_interviewer] Started interview: {role} ({difficulty})")

        return {
            "interview_id": interview_id,
            "role": role,
            "difficulty": difficulty,
            "question": first_question,
            "question_number": 1,
            "total_questions": 5
        }

    def generate_question(self, topic: str, difficulty: str = "medium",
                        question_type: str = "behavioral") -> dict:
        """
        Generate a specific interview question.
        """
        difficulty_instruction = {
            "easy": "basic, entry-level questions",
            "medium": "moderate difficulty, standard interview questions",
            "hard": "challenging questions requiring deep expertise",
            "expert": "highly complex questions for senior positions"
        }

        type_prompts = {
            "behavioral": "STAR-format behavioral questions about past experiences",
            "technical": "Technical questions testing knowledge and problem-solving",
            "situational": "Hypothetical scenarios testing decision-making",
            "brain_teaser": "Analytical puzzles and logic problems",
            "system_design": "Architecture and design pattern questions",
            "coding": "Programming and algorithm questions",
            "communication": "Communication and collaboration scenarios",
            "leadership": "Leadership and management style questions"
        }

        prompt = f"""Generate a single {difficulty} {question_type} interview question for a {topic} position.

Difficulty: {difficulty_instruction.get(difficulty, difficulty_instruction['medium'])}
Question Type: {type_prompts.get(question_type, type_prompts['behavioral'])}

Provide:
1. The question text
2. What the interviewer is looking for
3. A sample strong answer structure
4. Common mistakes to avoid

Format clearly with headers.
"""

        try:
            question_data = _llm(prompt, max_tokens=800)

            question = {
                "id": str(uuid.uuid4()),
                "topic": topic,
                "difficulty": difficulty,
                "type": question_type,
                "question": self._extract_question_text(question_data),
                "full_prompt": question_data,
                "created_at": self._get_timestamp()
            }

            self._question_history.append(question)

            return question

        except Exception as e:
            logger.error(f"[VECTOR][mock_interviewer] Question generation failed: {e}")
            return {"topic": topic, "error": str(e)}

    def _extract_question_text(self, full_prompt: str) -> str:
        """Extract the actual question from the full prompt response."""
        lines = full_prompt.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("**") and len(stripped) > 10:
                if any(q in stripped.lower() for q in ["describe", "tell me", "how would", "what is", "can you", "when", "why"]):
                    return stripped
        return lines[0] if lines else full_prompt[:200]

    def evaluate_answer(self, question_id: str, answer: str) -> dict:
        """
        Evaluate a candidate's answer to an interview question.
        """
        question = None
        for q in self._question_history:
            if q["id"] == question_id:
                question = q
                break

        if not question:
            return {"status": "error", "message": "Question not found"}

        prompt = f"""Evaluate this interview answer for a {question['topic']} position.

Question: {question.get('question', 'N/A')}
Difficulty: {question['difficulty']}
Type: {question['type']}

Candidate's Answer:
{answer}

Provide evaluation with:
1. Overall Score (1-10)
2. Strengths (bullet points)
3. Areas for Improvement (bullet points)
4. Suggested Answer (brief)
5. Tips for Better Response

Be honest, constructive, and specific.
"""

        try:
            evaluation = _llm(prompt, max_tokens=1000)
            score = self._extract_score(evaluation)

            evaluation_data = {
                "id": str(uuid.uuid4()),
                "question_id": question_id,
                "answer": answer,
                "evaluation": evaluation,
                "score": score,
                "topic": question["topic"],
                "evaluated_at": self._get_timestamp()
            }

            self._evaluation_cache.append(evaluation_data)

            self.award_points(score * 2, "answer_evaluated")
            logger.info(f"[VECTOR][mock_interviewer] Answer evaluated: score={score}/10")

            return evaluation_data

        except Exception as e:
            logger.error(f"[VECTOR][mock_interviewer] Evaluation failed: {e}")
            return {"question_id": question_id, "error": str(e)}

    def _extract_score(self, evaluation: str) -> int:
        """Extract numeric score from evaluation text."""
        import re
        match = re.search(r'[Ss]core[:\s]*(\d+)', evaluation)
        if match:
            return min(10, max(1, int(match.group(1))))
        return 5

    def get_next_question(self, interview_id: str) -> Optional[dict]:
        """Get the next question in the interview."""
        if interview_id not in self._active_interviews:
            return None

        interview = self._active_interviews[interview_id]

        if interview["current_question"] >= interview["total_questions"]:
            interview["status"] = "completed"
            return {"status": "completed", "interview_id": interview_id}

        question_types = ["behavioral", "technical", "situational", "behavioral", "technical"]
        q_type = question_types[interview["current_question"] % len(question_types)]

        question = self.generate_question(
            interview["role"],
            interview["difficulty"],
            q_type
        )

        interview["questions"].append(question)
        interview["current_question"] += 1

        return {
            "interview_id": interview_id,
            "question": question,
            "question_number": interview["current_question"],
            "total_questions": interview["total_questions"]
        }

    def end_interview(self, interview_id: str) -> dict:
        """End interview and return final summary."""
        if interview_id not in self._active_interviews:
            return {"status": "error", "message": "Interview not found"}

        interview = self._active_interviews[interview_id]
        interview["status"] = "completed"
        interview["ended_at"] = self._get_timestamp()

        total_score = sum(
            e["score"] for e in self._evaluation_cache
            if e["question_id"] in [q["id"] for q in interview["questions"]]
        )

        avg_score = total_score / max(len(interview["questions"]), 1)

        summary = {
            "interview_id": interview_id,
            "role": interview["role"],
            "difficulty": interview["difficulty"],
            "questions_asked": len(interview["questions"]),
            "average_score": round(avg_score, 1),
            "total_score": total_score,
            "duration": self._calculate_duration(interview),
            "status": "completed",
            "recommendations": self._generate_recommendations(avg_score)
        }

        self.award_points(int(avg_score * 5), f"interview_completed_{interview['role']}")
        logger.info(f"[VECTOR][mock_interviewer] Interview completed: avg={avg_score:.1f}")

        return summary

    def _calculate_duration(self, interview: dict) -> str:
        """Calculate interview duration."""
        start = interview.get("started_at", "")
        end = interview.get("ended_at", self._get_timestamp())
        return f"{interview.get('current_question', 0)} questions"

    def _generate_recommendations(self, score: float) -> list[str]:
        """Generate recommendations based on score."""
        if score >= 8:
            return ["Great performance! Focus on maintaining consistency",
                   "Work on handling unexpected follow-up questions"]
        elif score >= 6:
            return ["Good effort. Strengthen technical depth",
                   "Practice more STAR-format responses",
                   "Work on specific examples from your experience"]
        elif score >= 4:
            return ["Needs improvement. Review fundamentals",
                   "Practice behavioral questions daily",
                   "Focus on clearer communication"]
        return ["Significant gaps identified. Consider formal training",
                "Start with basic interview preparation",
                "Review job requirements thoroughly"]

    def get_interview_stats(self) -> dict:
        """Get statistics about mock interviews."""
        return {
            "total_interviews": len(self._active_interviews),
            "questions_generated": len(self._question_history),
            "answers_evaluated": len(self._evaluation_cache),
            "avg_score": round(
                sum(e["score"] for e in self._evaluation_cache) / max(len(self._evaluation_cache), 1),
                1
            ) if self._evaluation_cache else 0
        }

    def _get_timestamp(self) -> str:
        """Get current UTC timestamp."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


    def _answer_interview_question(self, query: str) -> str:
        """Answer a free-text question about interview prep, grounded in
        real capabilities (difficulty levels, question types, any active
        interview) instead of always generating a default question — same
        design-district #33 fix pattern."""
        active = getattr(self, "_active_interviews", None)
        active_ctx = f"{len(active)} interview(s) in progress." if active else "No interview in progress."
        prompt = (
            f"You are VECTOR's mock interview coach. {active_ctx} "
            f"Difficulty levels: {getattr(self, 'DIFFICULTY_LEVELS', 'easy/medium/hard')}. "
            f"Question types: {getattr(self, 'QUESTION_TYPES', 'technical/behavioral')}.\n\n"
            f"Owner asked: {query}\n\nAnswer specifically — do not just generate a random practice question "
            f"unless that's actually what was asked for."
        )
        try:
            return _llm(prompt, max_tokens=600, temperature=0.6) or "I need a bit more detail to help with that."
        except Exception as e:
            logger.warning(f"[VECTOR][mock_interviewer] answer failed: {e}")
            return "I ran into a problem answering that — try again in a moment."

    async def run(self, task: dict) -> dict:
        p = task.get("params", {})
        # 2026-07-28: run() never checked task["type"] — always generated
        # a "machine learning"/"medium" question regardless of what was
        # actually asked, ignoring free-text questions entirely. Same bug
        # class as design district's #33.
        query = p.get("query") or p.get("content") or task.get("query")
        if query and not p.get("topic"):
            return {"status": "ok", "response": self._answer_interview_question(query)}
        q = self.generate_question(p.get("topic", "machine learning"), p.get("difficulty", "medium"))
        if "error" in q:
            return {"status": "error", "error": q["error"], "question": q}
        return {"status": "ok", "question": q}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    interviewer = MockInterviewer()

    interview = interviewer.start_interview("Software Engineer", "medium")
    print(f"Started interview: {interview['interview_id'][:20]}...")
    print(f"First question: {interview['question'].get('question', 'N/A')[:50]}...")

    print("✅ mock_interviewer.py OK")
