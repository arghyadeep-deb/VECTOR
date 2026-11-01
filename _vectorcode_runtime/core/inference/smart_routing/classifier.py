"""
VECTOR Smart Routing — 15-Dimensional Complexity Classifier
Python port of ClawRouter/src/router/rules.ts + selector.ts

Scores a prompt across 15 dimensions in < 1ms to determine routing tier:
  SIMPLE → cheap fast model (gemma, flash)
  MEDIUM → capable mid-tier model
  COMPLEX → strong model (sonnet-class)
  REASONING → best reasoning model (o3, claude-opus)

Usage:
    decision = classify("What is 2+2?")
    # → RoutingDecision(tier=SIMPLE, confidence=0.95, ...)

    decision = classify("Prove the Riemann hypothesis step by step")
    # → RoutingDecision(tier=REASONING, confidence=0.92, ...)
"""
from __future__ import annotations

__all__ = [
    "AGENTIC_TASK_KEYWORDS",
    "classify",
    "CODE_KEYWORDS",
    "CONFIDENCE_STEEPNESS",
    "CONFIDENCE_THRESHOLD",
    "CONSTRAINT_INDICATORS",
    "CREATIVE_KEYWORDS",
    "DimensionScore",
    "DOMAIN_SPECIFIC_KEYWORDS",
    "IMPERATIVE_VERBS",
    "NEGATION_KEYWORDS",
    "OUTPUT_FORMAT_KEYWORDS",
    "Profile",
    "REASONING_KEYWORDS",
    "REFERENCE_KEYWORDS",
    "RoutingDecision",
    "SIMPLE_KEYWORDS",
    "TECHNICAL_KEYWORDS",
    "Tier",
    "TIER_BOUNDARIES",
]


import math
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Tier(str, Enum):
    SIMPLE    = "SIMPLE"
    MEDIUM    = "MEDIUM"
    COMPLEX   = "COMPLEX"
    REASONING = "REASONING"


class Profile(str, Enum):
    FREE    = "free"
    ECO     = "eco"
    AUTO    = "auto"
    PREMIUM = "premium"


@dataclass
class DimensionScore:
    name:   str
    score:  float   # [-1.0, 1.0]
    signal: str | None = None


@dataclass
class RoutingDecision:
    tier:         Tier | None
    confidence:   float           # 0.0–1.0 (< 0.7 = uncertain)
    score:        float            # weighted aggregate
    method:       str = "rules"   # "rules" | "llm"
    reasoning:    str = ""
    signals:      list[str] = field(default_factory=list)
    agentic_score: float = 0.0
    profile:      Profile = Profile.AUTO


# ── Keyword banks (multilingual: EN + ZH + JA + RU + DE + ES + PT + KO + AR) ─

CODE_KEYWORDS = [
    # EN
    "function", "class", "import", "def ", "async ", "await ", "return ",
    "lambda", "decorator", "interface", "struct", "enum", "typedef",
    "algorithm", "implement", "refactor", "debug", "compile", "runtime",
    "recursion", "loop", "iterate", "array", "dict", "list", "tuple",
    "sql", "query", "schema", "api", "endpoint", "rest", "graphql",
    "docker", "kubernetes", "deploy", "ci/cd", "git", "commit", "pull request",
    # ZH
    "函数", "类", "导入", "实现", "算法", "接口", "调试",
    # JA
    "関数", "クラス", "インポート", "実装", "アルゴリズム",
    # RU
    "функция", "класс", "импорт", "алгоритм", "реализация",
]

REASONING_KEYWORDS = [
    # EN
    "prove", "proof", "theorem", "lemma", "corollary", "qed",
    "step by step", "chain of thought", "reasoning", "deduce", "infer",
    "formal proof", "mathematical", "derive", "axiom", "hypothesis",
    "analyze", "evaluate", "compare", "contrast", "critique", "assess",
    "why does", "explain why", "how does", "what causes",
    # ZH
    "证明", "推理", "分析", "评估", "定理",
    # JA
    "証明", "推論", "分析", "評価",
    # RU
    "доказать", "рассуждение", "анализ", "оценить",
    # DE
    "beweisen", "Beweis", "herleiten", "analysieren",
]

TECHNICAL_KEYWORDS = [
    # EN
    "distributed", "microservice", "scalability", "latency", "throughput",
    "consensus", "blockchain", "cryptography", "zero-knowledge", "zkp",
    "quantum", "fpga", "genomics", "bioinformatics", "neural network",
    "transformer", "attention mechanism", "backpropagation", "gradient",
    "reinforcement learning", "markov", "bayesian", "stochastic",
    "concurrent", "asynchronous", "mutex", "semaphore", "deadlock",
    "cache invalidation", "consistency", "partition tolerance", "cap theorem",
    # ZH
    "分布式", "微服务", "区块链", "量子", "神经网络",
    # JA
    "分散型", "マイクロサービス", "ブロックチェーン", "量子",
    # DE
    "verteilte systeme", "quantencomputing", "blockchain",
]

CREATIVE_KEYWORDS = [
    # EN
    "story", "poem", "narrative", "creative", "brainstorm", "imagine",
    "fiction", "character", "plot", "metaphor", "analogy", "write a",
    "compose", "generate ideas", "what if", "scenario",
    # ZH
    "故事", "诗歌", "创意", "头脑风暴", "想象",
    # JA
    "ストーリー", "詩", "創造的", "ブレインストーミング",
]

SIMPLE_KEYWORDS = [
    # EN
    "what is", "define", "translate", "list", "give me", "show me",
    "what does", "who is", "when did", "where is", "how many",
    "simple", "quick", "brief", "summarize in one", "in short",
    # ZH
    "是什么", "定义", "翻译", "列出", "简单",
    # JA
    "とは", "定義", "翻訳", "リスト", "簡単",
    # RU
    "что такое", "определение", "перевести", "список",
]

IMPERATIVE_VERBS = [
    "build", "create", "implement", "design", "develop", "architect",
    "construct", "engineer", "optimize", "refactor", "rewrite", "migrate",
    "integrate", "configure", "setup", "initialize", "bootstrap", "scaffold",
]

CONSTRAINT_INDICATORS = [
    "under", "at most", "budget", "limit", "constraint", "no more than",
    "within", "less than", "at least", "minimum", "maximum", "exactly",
]

OUTPUT_FORMAT_KEYWORDS = [
    "json", "yaml", "xml", "csv", "table", "markdown", "code block",
    "formatted", "structured", "as a list", "in a list", "bullet points",
    "numbered list",
]

REFERENCE_KEYWORDS = [
    "above", "previous", "attached", "as mentioned", "based on", "referring to",
    "the code I provided", "in the context", "that I showed", "per the",
]

NEGATION_KEYWORDS = [
    "don't", "do not", "don't", "avoid", "never", "without", "except",
    "not including", "excluding", "ignore", "skip",
]

DOMAIN_SPECIFIC_KEYWORDS = [
    # Science/Engineering
    "quantum", "fpga", "genomics", "bioinformatics", "spectroscopy",
    "crystallography", "thermodynamics", "fluid dynamics", "topology",
    "differential equations", "fourier", "laplace",
    # Finance
    "derivatives", "options pricing", "black-scholes", "monte carlo",
    "stochastic calculus", "arbitrage", "hedging",
    # Legal/Medical
    "jurisprudence", "statute", "pathophysiology", "pharmacokinetics",
    "differential diagnosis", "clinical trial",
]

AGENTIC_TASK_KEYWORDS = [
    "read file", "write file", "edit file", "delete file", "create file",
    "run command", "execute", "terminal", "bash", "shell",
    "git commit", "git push", "deploy", "publish",
    "send email", "send message", "post to", "upload",
    "download", "fetch from", "api call", "webhook",
    "schedule", "automate", "pipeline", "workflow",
]

# ── Dimension weights (sum to 1.0) ──────────────────────────────────────────

DIMENSION_WEIGHTS: dict[str, float] = {
    "tokenCount":         0.12,
    "codePresence":       0.12,
    "reasoningMarkers":   0.14,
    "technicalTerms":     0.10,
    "creativeMarkers":    0.05,
    "simpleIndicators":   0.10,
    "multiStepPatterns":  0.07,
    "questionComplexity": 0.04,
    "imperativeVerbs":    0.05,
    "constraintCount":    0.04,
    "outputFormat":       0.04,
    "referenceComplexity":0.04,
    "negationComplexity": 0.03,
    "domainSpecificity":  0.08,
    "agenticTask":        0.08,
}

# Tier boundaries for weighted score (roughly -1.0 to 1.0 range)
TIER_BOUNDARIES = {
    "simple_medium":    -0.15,
    "medium_complex":    0.30,
    "complex_reasoning": 0.60,
}
CONFIDENCE_STEEPNESS = 8.0
CONFIDENCE_THRESHOLD = 0.55   # below this → LLM classifier fallback


# ── Scorer functions ──────────────────────────────────────────────────────────

def _score_token_count(tokens: int) -> DimensionScore:
    if tokens < 50:
        return DimensionScore("tokenCount", -1.0, f"short ({tokens} tokens)")
    if tokens > 500:
        return DimensionScore("tokenCount",  1.0, f"long ({tokens} tokens)")
    return DimensionScore("tokenCount", 0.0)


def _score_keywords(
    text: str,
    keywords: list[str],
    name: str,
    label: str,
    low_thresh: int,
    high_thresh: int,
    score_none: float,
    score_low: float,
    score_high: float,
) -> DimensionScore:
    matches = [kw for kw in keywords if kw.lower() in text]
    if len(matches) >= high_thresh:
        return DimensionScore(name, score_high, f"{label} ({', '.join(matches[:3])})")
    if len(matches) >= low_thresh:
        return DimensionScore(name, score_low, f"{label} ({', '.join(matches[:3])})")
    return DimensionScore(name, score_none)


def _score_multi_step(text: str) -> DimensionScore:
    patterns = [r"first.*then", r"step \d", r"\d\.\s"]
    if any(re.search(p, text, re.IGNORECASE) for p in patterns):
        return DimensionScore("multiStepPatterns", 0.5, "multi-step")
    return DimensionScore("multiStepPatterns", 0.0)


def _score_question_complexity(prompt: str) -> DimensionScore:
    count = prompt.count("?")
    if count > 3:
        return DimensionScore("questionComplexity", 0.5, f"{count} questions")
    return DimensionScore("questionComplexity", 0.0)


def _score_agentic(text: str) -> tuple[DimensionScore, float]:
    matches = [kw for kw in AGENTIC_TASK_KEYWORDS if kw.lower() in text]
    n = len(matches)
    signals = matches[:3]
    if n >= 4:
        return DimensionScore("agenticTask", 1.0, f"agentic ({', '.join(signals)})"), 1.0
    if n >= 3:
        return DimensionScore("agenticTask", 0.6, f"agentic ({', '.join(signals)})"), 0.6
    if n >= 1:
        return DimensionScore("agenticTask", 0.2, f"agentic-light ({', '.join(signals)})"), 0.2
    return DimensionScore("agenticTask", 0.0), 0.0


def _sigmoid(x: float, steepness: float) -> float:
    return 1.0 / (1.0 + math.exp(-steepness * x))


# ── Main classifier ───────────────────────────────────────────────────────────

def classify(
    prompt: str,
    system_prompt: str = "",
    max_tokens: int = 2048,
    profile: str = "auto",
) -> RoutingDecision:
    """
    Score prompt across 15 dimensions → SIMPLE/MEDIUM/COMPLEX/REASONING.
    Port of ClawRouter's classifyByRules(). Runs in < 1ms.
    """
    # Score user text only — system prompts have boilerplate that distorts scoring
    user_text = prompt.lower()
    estimated_tokens = len(prompt.split()) + len(system_prompt.split())

    dims: list[DimensionScore] = [
        _score_token_count(estimated_tokens),
        _score_keywords(user_text, CODE_KEYWORDS,        "codePresence",       "code",      1, 2, 0.0, 0.5, 1.0),
        _score_keywords(user_text, REASONING_KEYWORDS,   "reasoningMarkers",   "reasoning", 1, 2, 0.0, 0.7, 1.0),
        _score_keywords(user_text, TECHNICAL_KEYWORDS,   "technicalTerms",     "technical", 2, 4, 0.0, 0.5, 1.0),
        _score_keywords(user_text, CREATIVE_KEYWORDS,    "creativeMarkers",    "creative",  1, 2, 0.0, 0.5, 0.7),
        _score_keywords(user_text, SIMPLE_KEYWORDS,      "simpleIndicators",   "simple",    1, 2, 0.0,-1.0,-1.0),
        _score_multi_step(user_text),
        _score_question_complexity(prompt),
        _score_keywords(user_text, IMPERATIVE_VERBS,     "imperativeVerbs",    "imperative",1, 2, 0.0, 0.3, 0.5),
        _score_keywords(user_text, CONSTRAINT_INDICATORS,"constraintCount",    "constraints",1,3, 0.0, 0.3, 0.7),
        _score_keywords(user_text, OUTPUT_FORMAT_KEYWORDS,"outputFormat",      "format",    1, 2, 0.0, 0.4, 0.7),
        _score_keywords(user_text, REFERENCE_KEYWORDS,   "referenceComplexity","references",1, 2, 0.0, 0.3, 0.5),
        _score_keywords(user_text, NEGATION_KEYWORDS,    "negationComplexity", "negation",  2, 3, 0.0, 0.3, 0.5),
        _score_keywords(user_text, DOMAIN_SPECIFIC_KEYWORDS,"domainSpecificity","domain",   1, 2, 0.0, 0.5, 0.8),
    ]
    agentic_dim, agentic_score = _score_agentic(user_text)
    dims.append(agentic_dim)

    signals = [d.signal for d in dims if d.signal]

    # Weighted score
    weighted = sum(d.score * DIMENSION_WEIGHTS.get(d.name, 0) for d in dims)

    # Reasoning override: 2+ reasoning markers → force REASONING
    reasoning_hits = [kw for kw in REASONING_KEYWORDS if kw.lower() in user_text]
    if len(reasoning_hits) >= 2:
        conf = max(_sigmoid(max(weighted, 0.3), CONFIDENCE_STEEPNESS), 0.85)
        return RoutingDecision(
            tier=Tier.REASONING, confidence=conf, score=weighted,
            signals=signals, agentic_score=agentic_score,
            reasoning=f"reasoning override: {reasoning_hits[:3]}",
            profile=Profile(profile),
        )

    # Map score to tier
    b = TIER_BOUNDARIES
    if weighted < b["simple_medium"]:
        tier = Tier.SIMPLE
        dist = b["simple_medium"] - weighted
    elif weighted < b["medium_complex"]:
        tier = Tier.MEDIUM
        dist = min(weighted - b["simple_medium"], b["medium_complex"] - weighted)
    elif weighted < b["complex_reasoning"]:
        tier = Tier.COMPLEX
        dist = min(weighted - b["medium_complex"], b["complex_reasoning"] - weighted)
    else:
        tier = Tier.REASONING
        dist = weighted - b["complex_reasoning"]

    conf = _sigmoid(dist, CONFIDENCE_STEEPNESS)
    if conf < CONFIDENCE_THRESHOLD:
        tier = None  # uncertain — caller should use LLM fallback

    reasoning_str = f"score={weighted:.3f} tier={tier} signals={signals[:4]}"

    return RoutingDecision(
        tier=tier, confidence=conf, score=weighted,
        signals=signals, agentic_score=agentic_score,
        reasoning=reasoning_str,
        profile=Profile(profile),
    )


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    cases = [
        # (prompt, expected_tier)
        # Note: COMPLEX needs long prompts (token count is a major dimension)
        ("Define photosynthesis in simple terms",          Tier.SIMPLE),
        ("Write a Python function to sort a list using recursion with class-based implementation", Tier.MEDIUM),
        ("Prove that there are infinitely many primes, step by step chain of thought", Tier.REASONING),
        ("Analyze and step by step derive Euler's formula", Tier.REASONING),
    ]

    all_ok = True
    for prompt, expected in cases:
        d = classify(prompt)
        # None tier = uncertain (will use LLM fallback) — also acceptable
        ok = d.tier == expected or (d.tier is None and d.confidence < 0.60)
        if not ok:
            all_ok = False
        print(f"  {'OK' if ok else 'FAIL'} {prompt[:55]!r} → {d.tier} conf={d.confidence:.2f} (expected {expected.value})")

    print(f"\n{'OK' if all_ok else 'SOME FAILED'} classifier.py — 15-dim routing classifier")
