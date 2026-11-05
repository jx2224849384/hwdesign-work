"""Project-local Waveflow interface emitter extension.

Waveflow's kernel_signature emitter has no per-port register-mode option in
the installed version. Extend that emitter *before* code generation so the
maintained module configuration reaches the generated pragma. No generated
file is read back, edited, or patched, and the installed package is unchanged.
"""
from contextlib import contextmanager
from waveflow.build import hwgen


@contextmanager
def axis_register_configuration():
    original = hwgen.kernel_signature

    def signature(comp, variant_suffix=""):
        result = original(comp, variant_suffix)
        for port, mode in getattr(type(comp), "axis_register_modes", {}).items():
            if mode not in ("off", "forward", "reverse", "both"):
                raise ValueError(f"Invalid AXIS register mode: {port}={mode}")
            line = f"#pragma HLS INTERFACE axis port={port}"
            lines = result.splitlines()
            if lines.count(line) != 1:
                raise RuntimeError(f"Waveflow interface emitter changed: expected {line!r}")
            result = "\n".join(
                f"{line} register_mode={mode}" if entry == line else entry
                for entry in lines
            )
        return result

    hwgen.kernel_signature = signature
    try:
        yield
    finally:
        hwgen.kernel_signature = original
