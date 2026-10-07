"""Out-of-tree vLLM plugin for deadline-bounded KV write-back (Phase 3).

`core` is plain Python; `manager` imports vLLM and is loaded by vLLM itself through
`spec_module_path`.
"""
