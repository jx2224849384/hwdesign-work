"""Wire schemas, exact arithmetic, and the Waveflow-generated HLS boundary."""
from dataclasses import dataclass, field
from typing import ClassVar
import numpy as np
from waveflow.hw.dataschema import DataList, IntField
from waveflow.hw.hw_hostactivated import HostActivated
from waveflow.hw.hw_module import HwParam
from waveflow.hw.clock import Clock
from waveflow.hw.interface import StreamIFMaster, StreamIFSlave
from waveflow.hw.regmap import Bit, RegAccess, RegField, VitisRegMap, VitisRegMapMMIFSlave

U32 = IntField.specialize(bitwidth=32, signed=False, include_dir="include")
I32 = IntField.specialize(bitwidth=32, signed=True, include_dir="include")
I64 = IntField.specialize(bitwidth=64, signed=True, include_dir="include")
U8 = IntField.specialize(bitwidth=8, signed=False)

class CmdHdr(DataList):
    elements = {k: {"schema": U32} for k in ("opcode", "tx_id", "arg0", "arg1")}

class RespHdr(DataList):
    elements = {k: {"schema": U32} for k in ("opcode", "tx_id", "rows")}

SCHEMAS = [CmdHdr, RespHdr]

def matvec_eval(a, x):
    """Scalar, exact integer golden independent of NumPy's matrix multiplication."""
    a = np.asarray(a)
    x = np.asarray(x)
    assert a.ndim == 2 and x.ndim == 1 and a.shape[1] == len(x)
    assert 1 <= a.shape[0] <= 16 and 1 <= a.shape[1] <= 16
    assert np.all((a >= -32768) & (a <= 32767)) and np.all((x >= -32768) & (x <= 32767))
    result = []
    for row in a:
        acc = 0
        for left, right in zip(row, x):
            product = int(left) * int(right)
            assert -(1 << 31) <= product < (1 << 31)
            acc += product
        result.append(acc)
    return np.asarray(result, dtype=np.int64)

@dataclass
class MatvecAccel(HostActivated):
    cpp_kernel_name: ClassVar[str | None] = "matvec"
    cpp_namespace: ClassVar[str | None] = "matvec_impl"
    cpp_body: ClassVar[str | None] = "body"
    axis_register_modes: ClassVar[dict[str, str]] = {"s_in": "off", "m_out": "both"}
    in_bw: HwParam[int] = 32
    out_bw: HwParam[int] = 32
    aximm_bw: HwParam[int] = 32
    clk: Clock = field(default_factory=lambda: Clock(freq=100e6))

    def __post_init__(self):
        super().__post_init__()
        self.s_in = StreamIFSlave(name=f"{self.name}_s_in", sim=self.sim, bitwidth=self.in_bw)
        self.m_out = StreamIFMaster(name=f"{self.name}_m_out", sim=self.sim, bitwidth=self.out_bw)
        self.regmap = VitisRegMap({"halted": RegField(U32, RegAccess.R),
                                  "error": RegField(U32, RegAccess.R),
                                  "tx_id": RegField(U32, RegAccess.R)}, bitwidth=32)
        self.s_lite = VitisRegMapMMIFSlave(name=f"{self.name}_s_lite", sim=self.sim,
             bitwidth=32, regmap=self.regmap, on_start=self.on_start)
        for ep in (self.s_in, self.m_out, self.s_lite):
            self.add_endpoint(ep)

    def body(self, input_bursts):
        """Untimed functional twin. This assignment explicitly excludes a timing model."""
        from protocol_model import matvec_stream_model
        return matvec_stream_model(input_bursts)
