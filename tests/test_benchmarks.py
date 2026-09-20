from pathlib import Path

from lean_proof_agent.benchmarks import list_benchmarks, load_benchmark_path


ROOT = Path(__file__).resolve().parents[1]


def test_bundled_suite_has_twenty_theorem_only_problems() -> None:
    problems = list_benchmarks()
    assert len(problems) == 20
    assert {problem.category for problem in problems} == {
        "arithmetic",
        "algebra",
        "logic",
        "lists",
        "sets",
        "inequalities",
    }
    assert all(":=" not in problem.theorem for problem in problems)


def test_load_benchmark_path_accepts_file_and_directory() -> None:
    assert len(load_benchmark_path(ROOT / "benchmarks")) == 20
    one = load_benchmark_path(ROOT / "benchmarks" / "add_zero.json")
    assert [problem.name for problem in one] == ["add_zero"]
