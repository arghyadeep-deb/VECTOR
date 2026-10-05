from vectorcode.src.learning.distillation.student_runner import VLLMStudentRunner


class _Client:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_student_runner_context_manager_closes_owned_client() -> None:
    runner = object.__new__(VLLMStudentRunner)
    runner._client = _Client()

    with runner as entered:
        assert entered is runner

    assert runner._client.closed is True
