"""Pydantic models for adaptive training configuration."""


__all__ = [
    "AdapterConfig",
    "EvalConfig",
    "TrainingArgs",
]


from pydantic import BaseModel, Field


class AdapterConfig(BaseModel):
    # This value becomes a directory name below the configured adapters root.
    # Reject separators, drive prefixes, and the special dot components before
    # pathlib can interpret them and escape that root.
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    base_model: str
    target_modules: list[str]
    rank: int = Field(default=16, ge=1, le=256)
    alpha: float = Field(default=16.0, ge=1.0, le=512.0)
    dropout: float = Field(default=0.05, ge=0.0, le=0.5)
    dataset_path: str = ""
    save_dir: str = ""


class TrainingArgs(BaseModel):
    learning_rate: float = Field(default=2e-4, gt=0.0, le=1.0)
    num_epochs: int = Field(default=3, ge=1, le=100)
    batch_size: int = Field(default=4, ge=1, le=512)
    max_seq_length: int = Field(default=2048, ge=64, le=32768)
    warmup_steps: int = Field(default=100, ge=0, le=10000)
    gradient_accumulation_steps: int = Field(default=4, ge=1, le=64)


class EvalConfig(BaseModel):
    benchmark_prompts_path: str = ""
    scoring_method: str = Field(default="exact_match", pattern=r"^(exact_match|rubric|llm_judge)$")
    pass_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
