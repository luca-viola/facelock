"""onnxruntime sessions set up to use as little memory and as few threads as possible.

Measured with buffalo_l on an RTX 5060 Ti: the defaults started a thread per core
for every model and an exhaustive cuDNN algorithm search, and the GPU runtime
alone costs several hundred MB of RAM and VRAM. On the CPU these settings use
about a third of the RAM, at about 0.1 s per snap.
"""

import importlib.util
import os
import sys

from .base import CPU, GPU

CUDA_PROVIDER = "CUDAExecutionProvider"
COREML_PROVIDER = "CoreMLExecutionProvider"
GPU_PROVIDER = COREML_PROVIDER if sys.platform == "darwin" else CUDA_PROVIDER
CPU_PROVIDER = "CPUExecutionProvider"
CPU_THREADS = min(4, os.cpu_count() or 1)
CUDA_OPTIONS = {
    "cudnn_conv_algo_search": "HEURISTIC",  # the exhaustive search costs memory and startup time
    "arena_extend_strategy": "kSameAsRequested",
    "cudnn_conv_use_max_workspace": "0",
}


COREML_OPTIONS = {"ModelFormat": "MLProgram"}


def gpu_provider_available():
    """Whether onnxruntime was built with CUDA (Linux) or CoreML (macOS)."""
    import onnxruntime

    return GPU_PROVIDER in onnxruntime.get_available_providers()


def _gpu_providers():
    if GPU_PROVIDER == CUDA_PROVIDER:
        if importlib.util.find_spec("nvidia") is not None:
            import onnxruntime

            # CUDA from pip is outside the library search path, so it has to be loaded first.
            onnxruntime.preload_dlls()
        return [(CUDA_PROVIDER, CUDA_OPTIONS), CPU_PROVIDER]
    return [(COREML_PROVIDER, COREML_OPTIONS), CPU_PROVIDER]


def create_session(path, compute):
    """Returns (session, the compute it actually got), falling back to the CPU."""
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.inter_op_num_threads = 1
    options.enable_cpu_mem_arena = False
    if compute == GPU and gpu_provider_available():
        options.intra_op_num_threads = 1  # the GPU does the work
        providers = _gpu_providers()
    else:
        options.intra_op_num_threads = CPU_THREADS
        # Prepacking keeps a second, rearranged copy of every weight.
        options.add_session_config_entry("session.disable_prepacking", "1")
        # Idle worker threads would otherwise spin, keeping extra cores busy for nothing.
        options.add_session_config_entry("session.intra_op.allow_spinning", "0")
        providers = [CPU_PROVIDER]
    session = onnxruntime.InferenceSession(path, options, providers=providers)
    actual = GPU if session.get_providers()[0] == GPU_PROVIDER else CPU
    return session, actual
