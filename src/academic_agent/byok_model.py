"""The shape of a BYOK visitor's model choice, without importing an LLM stack.

The API boundary (api/models.py, api/runs.py) validates and forwards the model
name; it must stay importable without crewai, so these constants live here
rather than in llm_config, which re-exports them.
"""

import re

#: A BYOK visitor may name the model their own key should use. Letters,
#: digits and . _ - : only, so it selects a model at the provider's fixed
#: endpoint but cannot carry a path, URL, query or prefix that redirects it.
BYOK_MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}")

#: The variable each provider reads its model from first. A BYOK worker gets
#: the visitor's model here after every operator model name is scrubbed (see
#: api/runs.py), so the run and its helpers resolve the same model.
MODEL_ENV_NAMES = {
    "deepseek": "DEEPSEEK_MODEL",
    "qwen": "QWEN_MODEL",
    "openai": "OPENAI_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
}
