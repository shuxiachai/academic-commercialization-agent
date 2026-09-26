"""Standalone positive-control entry; never discovers dotenv or credentials."""

from academic_agent.saved_source_positive_qwen_canary import main


if __name__ == "__main__":
    raise SystemExit(main())
