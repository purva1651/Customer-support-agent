from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_phase_one_scaffold_files_exist() -> None:
    required_files = (
        "pyproject.toml",
        "Makefile",
        ".env.example",
        "config/agent.yaml",
        "config/intents.yaml",
        "config/tools.yaml",
        "config/prompts.yaml",
    )

    assert all((ROOT / relative_path).is_file() for relative_path in required_files)
