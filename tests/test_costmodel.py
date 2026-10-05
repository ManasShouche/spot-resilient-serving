from kvevac.costmodel import crossover_tokens, recompute_s, transfer_s
from kvevac.profiles import GPUS, LINKS, MODELS, LinkProfile

M8 = MODELS["llama-3.1-8b"]


def test_kv_bytes_per_token_match_published_architectures() -> None:
    assert M8.kv_bytes_per_token == 128 * 1024
    assert MODELS["llama-3.1-70b"].kv_bytes_per_token == 320 * 1024


def test_recompute_is_superlinear_in_context() -> None:
    gpu = GPUS["l40s"]
    assert recompute_s(100_000, gpu) > 10 * recompute_s(10_000, gpu)


def test_short_contexts_favor_recompute_long_contexts_favor_transfer() -> None:
    # Qualitative ShuntServe finding: recompute wins except for long contexts / fast links.
    gpu, link = GPUS["l40s"], LINKS["10gbe"]
    assert recompute_s(1_000, gpu) < transfer_s(1_000, M8, link)
    assert transfer_s(100_000, M8, link) < recompute_s(100_000, gpu)


def test_crossover_moves_out_with_faster_prefill_and_slower_links() -> None:
    link = LINKS["10gbe"]
    slow_gpu = crossover_tokens(M8, GPUS["l4"], link)
    fast_gpu = crossover_tokens(M8, GPUS["h100"], link)
    assert slow_gpu is not None and fast_gpu is not None and slow_gpu < fast_gpu
    assert crossover_tokens(M8, GPUS["l4"], LINKS["25gbe"]) < slow_gpu


def test_wan_links_never_favor_transfer_at_realistic_contexts() -> None:
    wan = LinkProfile("wan", bytes_per_s=12.5e6, setup_s=0.5)
    assert crossover_tokens(M8, GPUS["h100"], wan) is None
