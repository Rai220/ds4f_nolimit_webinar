"""Fast-path patches for the pinned EXL3 overlay on vLLM 0.30.0.

Needed for CUDA graphs on any topology (EXL3 GEMM pretune) and for
TP x DP + expert parallel (EP loader, expert_map, DP input_ids gather).
Measured on 4x H100 2026-09-23, see docs/13-speed.md. Run after
install-runtime.sh copied overlay exl3.py into vLLM. All fragments are checked
before anything is written; a known marker means that edit is already applied.
"""
from pathlib import Path
import argparse
import sys

import vllm

EXL3 = "model_executor/layers/quantization/exl3.py"
RUNNER = "model_executor/layers/fused_moe/runner/moe_runner.py"
WORKER = "v1/worker/gpu_worker.py"

# (file, marker, [(old, new), ...]) — each old must occur exactly once.
EDITS = [
    (EXL3, "[dsv41-exl3-ep]", [(
        """            expert_id = local_id

        tp_rank = get_tensor_model_parallel_rank()
        tp_size = get_tensor_model_parallel_world_size()
        suffix = _suffix_from_mapped_name(weight_name)
""",
        """            expert_id = local_id

        # [dsv41-exl3-ep] Shard by the MoE group, not the attention TP group:
        # under expert parallel each expert stays whole (moe tp_size == 1).
        tp_rank = self.moe.tp_rank
        tp_size = self.moe.tp_size
        suffix = _suffix_from_mapped_name(weight_name)
""")]),
    (EXL3, "[dsv41-exl3-ep-map]", [(
        """    emap = getattr(layer, "expert_map", None)
    if emap is None:
        return None
    if emap.device != device or emap.dtype != torch.long:
        layer.expert_map = emap.to(device=device, dtype=torch.long)
    return layer.expert_map
""",
        """    emap = getattr(layer, "expert_map", None)
    if emap is None:
        return None
    if emap.device == device and emap.dtype == torch.long:
        return emap
    # [dsv41-exl3-ep-map] RoutedExperts.expert_map is a read-only property;
    # keep the pinned long copy beside it, rebuilt if the source map changes.
    cached = getattr(layer, "_exl3_pinned_expert_map", None)
    if cached is None or cached[0] is not emap:
        cached = (emap, emap.to(device=device, dtype=torch.long))
        layer._exl3_pinned_expert_map = cached
    return cached[1]
""")]),
    (RUNNER, "[dsv41-dp-input-ids]", [
        ("""    def _maybe_dispatch(
        self,
        hidden_states: torch.Tensor,
        router_logits: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        # For naive dispatch/combine Dp/Ep, dispatch the hidden states and
        # router logits to all experts.
        # NOTE: this will be removed once all kernels are migrated into the
        # MoEKernel framework.
        if self.do_naive_dispatch_combine:
            result = get_ep_group().dispatch_router_logits(
                hidden_states,
                router_logits,
                self.moe_config.is_sequence_parallel,
            )
            assert len(result) == 2
            hidden_states, router_logits = result
""",
         """    def _maybe_dispatch(
        self,
        hidden_states: torch.Tensor,
        router_logits: torch.Tensor,
        input_ids: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor | None]:
        # For naive dispatch/combine Dp/Ep, dispatch the hidden states and
        # router logits to all experts.
        # NOTE: this will be removed once all kernels are migrated into the
        # MoEKernel framework.
        if self.do_naive_dispatch_combine:
            # [dsv41-dp-input-ids] Routers that read input_ids (DSv4 hash
            # tables, V4.1 vision bias) index them per gathered row, so the
            # ids must be gathered exactly like the hidden states.
            gather_ids = (
                input_ids is not None
                and input_ids.shape[0] == hidden_states.shape[0]
            )
            result = get_ep_group().dispatch_router_logits(
                hidden_states,
                router_logits,
                self.moe_config.is_sequence_parallel,
                extra_tensors=[input_ids] if gather_ids else None,
            )
            if gather_ids:
                hidden_states, router_logits, (input_ids,) = result
            else:
                assert len(result) == 2
                hidden_states, router_logits = result
"""),
        ("""            router_logits = get_pcp_group().all_gather(router_logits, dim=0)

        return hidden_states, router_logits
""",
         """            router_logits = get_pcp_group().all_gather(router_logits, dim=0)

        return hidden_states, router_logits, input_ids
"""),
        ("""            hidden_states, router_logits = self._maybe_dispatch(
                hidden_states,
                router_logits,
            )
""",
         """            hidden_states, router_logits, input_ids = self._maybe_dispatch(
                hidden_states,
                router_logits,
                input_ids,
            )
"""),
    ]),
]

WORKER_MARK = "[dsv41-exl3-pretune]"
WORKER_REQUIRED = (
    "class Worker(WorkerBase):",
    "    def compile_or_warm_up_model(self)",
    "    def determine_available_memory(self)",
    "\nimport os\n",
    "\nimport time\n",
)
WORKER_FOOTER = '''

# [dsv41-exl3-pretune] Ported from kit overlay/patch_memory_log.py (pretune part
# only): exllamav3 autotunes each new GEMM shape with cudaStreamSynchronize,
# which is illegal inside CUDA-graph capture (coop_autotune.cu:464). Touch every
# EXL3 shape once per row bucket before compile/capture. DSV41_EXL3_PRETUNE=0 skips.
def _dsv41_install_exl3_pretune() -> None:
    import functools
    import logging

    log = logging.getLogger("vllm.dsv41")

    def _pretune_once(self):
        # Capture can start in determine_available_memory (cudagraph memory
        # estimate) or in compile_or_warm_up_model; tune before whichever is first.
        if getattr(self, "_dsv41_pretuned", False):
            return
        self._dsv41_pretuned = True
        if os.environ.get("DSV41_EXL3_PRETUNE", "1") == "0":
            return
        try:
            from vllm.model_executor.layers.quantization import exl3 as _exl3

            runner = getattr(self, "model_runner", None)
            mods = [getattr(runner, "model", None)]
            for attr in ("speculator", "drafter"):
                spec = getattr(runner, attr, None)
                mods.append(getattr(spec, "model", None))
            sizes = tuple(
                int(v)
                for v in os.environ.get("DSV41_EXL3_PRETUNE_SIZES", "1,2,4,8,16").split(",")
                if v
            )
            t0 = time.perf_counter()
            shapes, launches = _exl3.pretune_exl3_shapes(mods, sizes=sizes)
            log.warning(
                "[dsv41-exl3-pretune] %d distinct shapes x %d row buckets = %d launches in %.1fs",
                shapes, len(sizes), launches, time.perf_counter() - t0,
            )
        except Exception as exc:  # never break the boot; capture will report
            log.warning("[dsv41-exl3-pretune] failed: %r", exc)

    for name in ("determine_available_memory", "compile_or_warm_up_model"):
        orig = getattr(Worker, name)
        if getattr(orig, "_dsv41_pretune_wrapped", False):
            continue

        def make(orig):
            @functools.wraps(orig)
            def wrapped(self, *args, **kwargs):
                _pretune_once(self)
                return orig(self, *args, **kwargs)

            wrapped._dsv41_pretune_wrapped = True
            return wrapped

        setattr(Worker, name, make(orig))


_dsv41_install_exl3_pretune()
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report state, write nothing")
    args = parser.parse_args()
    if vllm.__version__ != "0.30.0":
        print(f"This patch requires vLLM 0.30.0, found {vllm.__version__}", file=sys.stderr)
        return 1
    root = Path(vllm.__file__).parent
    texts: dict[str, str] = {}
    errors: list[str] = []
    for rel in (EXL3, RUNNER, WORKER):
        path = root / rel
        if not path.is_file():
            errors.append(f"missing {path}")
            continue
        texts[rel] = path.read_text()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    new = dict(texts)
    applied, present = [], []
    for rel, marker, edits in EDITS:
        if marker in new[rel]:
            present.append(marker)
            continue
        for old, _ in edits:
            n = new[rel].count(old)
            if n != 1:
                errors.append(f"{rel}: {marker} fragment found {n} times: {old.strip().splitlines()[0]!r}")
        if not errors:
            for old, repl in edits:
                new[rel] = new[rel].replace(old, repl)
            applied.append(marker)
    if WORKER_MARK in new[WORKER]:
        present.append(WORKER_MARK)
    else:
        for needle in WORKER_REQUIRED:
            if new[WORKER].count(needle) != 1:
                errors.append(f"{WORKER}: expected fragment {needle.strip()!r} once")
        if not errors:
            s = new[WORKER]
            new[WORKER] = (s if s.endswith("\n") else s + "\n") + WORKER_FOOTER
            applied.append(WORKER_MARK)
    if errors:
        print("Source differs from the reviewed vLLM 0.30.0 layout; nothing written:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.check:
        print(f"already applied: {present or 'none'}; would apply: {applied or 'none'}")
        return 0
    for rel, text in new.items():
        if text != texts[rel]:
            (root / rel).write_text(text)
    print(f"fast-path patches applied: {applied or 'none'}; already present: {present or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
