"""VECTOR × OpenMythos integration — vector-synthesizer-future training pipeline."""
from core.training.openmythos.trainer import (
    export_training_data,
    train,
    create_modelfile,
    check_setup,
)

__all__ = ["export_training_data", "train", "create_modelfile", "check_setup"]
