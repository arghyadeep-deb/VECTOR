"""Research benchmark: 15 prompts covering summarization, analysis, explanation, comparison."""


__all__ = [
    "RESEARCH_PROMPTS",
    "ResearchBenchmark",
]

from typing import Callable

from loguru import logger


RESEARCH_PROMPTS = [
    {"id": "summarize_attention", "prompt": "Summarize how attention mechanisms work in transformer models in 3-4 sentences.", "rubric": ["attention", "query", "key", "value", "weight", "context", "softmax"], "min_score": 0.5},
    {"id": "explain_backprop", "prompt": "Explain backpropagation to a junior developer. Cover the chain rule and gradient flow.", "rubric": ["chain", "gradient", "derivative", "layer", "loss", "weight"], "min_score": 0.5},
    {"id": "compare_rnn_transformer", "prompt": "Compare RNNs and Transformers for sequence modeling. Discuss strengths and weaknesses.", "rubric": ["sequential", "parallel", "attention", "long_range", "memory", "positional"], "min_score": 0.5},
    {"id": "analyze_bias_mitigation", "prompt": "Analyze bias mitigation strategies in LLMs. Cover data, training, and deployment phases.", "rubric": ["data", "training", "deployment", "fairness", "evaluation", "mitigation"], "min_score": 0.5},
    {"id": "explain_diffusion", "prompt": "Explain how diffusion models generate images. Include the forward and reverse process.", "rubric": ["noise", "denoise", "forward", "reverse", "gaussian", "sampling"], "min_score": 0.5},
    {"id": "summarize_rag", "prompt": "Summarize Retrieval-Augmented Generation (RAG) architecture and its benefits.", "rubric": ["retrieval", "augment", "generation", "vector", "context", "knowledge"], "min_score": 0.4},
    {"id": "compare_sgd_adam", "prompt": "Compare SGD and Adam optimizers. When would you choose one over the other?", "rubric": ["adaptive", "momentum", "learning_rate", "convergence", "noise"], "min_score": 0.5},
    {"id": "analyze_few_shot", "prompt": "Analyze how few-shot prompting affects LLM performance. Discuss in-context learning theories.", "rubric": ["few_shot", "in_context", "example", "learning", "prompt", "meta"], "min_score": 0.4},
    {"id": "explain_quantization", "prompt": "Explain model quantization techniques: GPTQ, AWQ, and GGUF. Trade-offs between size and quality.", "rubric": ["quantization", "precision", "int4", "int8", "calibration", "latency"], "min_score": 0.5},
    {"id": "summarize_rlhf", "prompt": "Summarize RLHF: reward modeling, PPO, and alignment tax.", "rubric": ["reward", "pppo", "alignment", "feedback", "preference", "policy"], "min_score": 0.4},
    {"id": "compare_lora_full_finetune", "prompt": "Compare LoRA with full fine-tuning. Discuss parameter efficiency, performance, and when to use each.", "rubric": ["lora", "adapter", "parameter_efficient", "fine_tune", "rank", "memory"], "min_score": 0.5},
    {"id": "analyze_embedding_quality", "prompt": "Analyze how embedding quality affects RAG performance. Discuss chunking, model choice, and dimensionality.", "rubric": ["embedding", "retrieval", "chunk", "dimension", "semantic", "similarity"], "min_score": 0.4},
    {"id": "explain_moe", "prompt": "Explain Mixture-of-Experts architecture. How does it enable larger models efficiently?", "rubric": ["expert", "router", "sparse", "gating", "efficiency", "capacity"], "min_score": 0.5},
    {"id": "summarize_evals", "prompt": "Summarize LLM evaluation approaches: benchmarks, human eval, and LLM-as-judge.", "rubric": ["benchmark", "evaluation", "judge", "human", "metric", "dataset"], "min_score": 0.5},
    {"id": "compare_oss_api_models", "prompt": "Compare open-source vs API-based LLMs for production use. Consider cost, privacy, latency, and quality.", "rubric": ["open_source", "api", "privacy", "cost", "latency", "control"], "min_score": 0.5},
]


class ResearchBenchmark:
    def __init__(self):
        self.prompts = RESEARCH_PROMPTS
        logger.info("[Benchmark] ResearchBenchmark initialized with {} prompts", len(self.prompts))

    def run(self, model_fn: Callable[[str], str]) -> dict[str, float]:
        scores = {}
        for p in self.prompts:
            try:
                response = model_fn(p["prompt"])
                score = self._score_response(p, response)
                scores[p["id"]] = score
                logger.debug("[Benchmark] {} scored {:.2f}", p["id"], score)
            except Exception as e:
                logger.warning("[Benchmark] {} failed: {}", p["id"], e)
                scores[p["id"]] = 0.0
        avg = sum(scores.values()) / max(len(scores), 1)
        logger.info("[Benchmark] Research average: {:.2f}/1.00", avg)
        return scores

    def _score_response(self, prompt: dict, response: str) -> float:
        if not response:
            return 0.0
        response_lower = response.lower()
        keywords = prompt["rubric"]
        if not keywords:
            return 1.0
        matches = sum(1 for k in keywords if k.replace("_", " ") in response_lower or k in response_lower)
        score = matches / len(keywords)
        min_len = 50
        length_factor = min(1.0, len(response.split()) / min_len)
        result = score * 0.7 + length_factor * 0.3
        return min(result, 1.0)
