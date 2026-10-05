import tomllib
from pathlib import Path

import pytest

from vectorcode.src.learning.distillation.execute.appliers.intelligence import (
    SetModelForQueryClassApplier,
    SetModelParamApplier,
)
from vectorcode.src.learning.distillation.execute.appliers.tools import (
    AddToolToAgentApplier,
    EditToolDescriptionApplier,
)
from vectorcode.src.learning.distillation.execute.base import ApplyContext
from vectorcode.src.learning.distillation.models import (
    Edit,
    EditOp,
    EditPillar,
    EditRiskTier,
)


def _edit(op: EditOp, payload: dict) -> Edit:
    return Edit(
        id="edit-1",
        pillar=EditPillar.INTELLIGENCE,
        op=op,
        target="target",
        rationale="test",
        expected_improvement="test",
        risk_tier=EditRiskTier.AUTO,
        payload=payload,
    )


@pytest.mark.parametrize(
    ("applier", "edit"),
    [
        (SetModelForQueryClassApplier(), _edit(EditOp.SET_MODEL_FOR_QUERY_CLASS, {"query_class": 'code\n[injected]', "model": 'model"\nflag = true'})),
        (SetModelParamApplier(), _edit(EditOp.SET_MODEL_PARAM, {"model": 'm"]\n[injected', "param": 'temperature\nflag', "value": 'x"\nflag = true'})),
        (AddToolToAgentApplier(), _edit(EditOp.ADD_TOOL_TO_AGENT, {"agent": 'a"]\n[injected', "tool_name": 'tool"\nflag = true'})),
        (EditToolDescriptionApplier(), _edit(EditOp.EDIT_TOOL_DESCRIPTION, {"tool_name": 'tool]\n[injected', "new_description": 'line\n"flag" = true'})),
    ],
)
def test_appliers_serialize_model_text_as_valid_toml(tmp_path: Path, applier, edit) -> None:
    context = ApplyContext(vector_home=tmp_path, session_id="session")
    applier.apply(edit, context)
    path = context.config_path if context.config_path.exists() else context.tools_dir / "descriptions.toml"

    with path.open("rb") as file:
        tomllib.load(file)
