"""Whether a usable GPU is present, asked of the driver or OS directly.

This doesn't start CUDA or CoreML in the process, so checking costs almost no
memory, unlike creating a GPU session just to see if one works.
"""

import ctypes
import logging
import platform
import sys

log = logging.getLogger("facelock")


def gpu_name():
    """Returns the first GPU's name, or None if there's no usable one."""
    if sys.platform == "darwin":
        return _apple_gpu_name()
    return _cuda_gpu_name()


def _apple_gpu_name():
    """Apple silicon runs models through CoreML on its GPU and Neural Engine."""
    if platform.machine() != "arm64":
        return None
    try:
        import onnxruntime
    except ImportError:
        return None
    if "CoreMLExecutionProvider" not in onnxruntime.get_available_providers():
        return None
    return "Apple silicon (CoreML)"


def _cuda_gpu_name():
    try:
        cuda = ctypes.CDLL("libcuda.so.1")
    except OSError:
        return None
    count = ctypes.c_int(0)
    if cuda.cuInit(0) != 0 or cuda.cuDeviceGetCount(ctypes.byref(count)) != 0 or count.value < 1:
        return None
    device = ctypes.c_int(0)
    name = ctypes.create_string_buffer(256)
    if cuda.cuDeviceGet(ctypes.byref(device), 0) != 0 or cuda.cuDeviceGetName(name, 256, device) != 0:
        return "NVIDIA GPU"
    return name.value.decode("utf-8", "replace")
