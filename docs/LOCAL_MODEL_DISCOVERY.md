# Local model inventory

ULTRON can inspect the model servers and model caches on the local machine.

The inventory uses bounded HTTP probes to fixed loopback addresses only. It does not
follow redirects, use environment proxies, download model files, start servers, or
read model weights. It can list Ollama, LM Studio, Jan, llama.cpp, vLLM, and LocalAI
servers, plus known Ollama, LM Studio, and Jan model folders.

The Local Models plugin is read-only. It reports model names, providers, running or
on-disk state, approximate parameter size, and detected capability hints. It does not
change provider settings or select a model for a conversation.

Automatic local fallback remains a separate feature. It requires explicit
local_fallback_consent and follows the 1.5B–3B quantized model policy.
