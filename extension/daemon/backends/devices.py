"""Whether a usable NVIDIA GPU is present, asked of the driver directly.

This doesn't start CUDA in the process, so checking costs almost no memory,
unlike creating a GPU session just to see if one works.
"""

import ctypes
import logging

log = logging.getLogger("faceguard")


def cuda_gpu_name():
    """Returns the first CUDA GPU's name, or None if the driver reports none."""
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
