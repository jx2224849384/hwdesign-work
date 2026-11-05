# Small matrix-vector accelerator

Implements [prompt revision 2](../prompt.md), with a fully documented **remaining RTL interface failure** in [results.md](../results.md): the generated AXIS input register slice accepts two extra beats after errors/END. Python, C simulation, and standard Vitis RTL co-simulation pass 85 scenarios, but the supplemental full-queue RTL test correctly fails all 85 exact input-consumption checks. Numerical outputs/status match; the no-read-ahead contract does not. This project must not be presented as fully passing hardware.

The report has all seven required sections and cites exact JSON entries, RTL handshake logs, and synthesis XML. Evidence is retained under `evidence/`, including failed attempts and both successful and failed checks. No Python timing model was implemented.

## Sources

- `matvec.py`: unsigned 32-bit command/response schemas, exact scalar integer model, status-only Waveflow boundary declaration.
- `protocol_model.py`: untimed beat protocol model, including framing/error priority and exact input consumption.
- `scenarios.py`: 85 activations, including 35 error/recovery pairs, signed/extreme/rectangular/reconfiguration cases and eight-vector performance sequence. Independent expectations use NumPy int64 @.
- `matvec_body_impl.tpp`: hand-written HLS body, staging/commit buffers and per-vector dot products.
- `matvec_tb.cpp`: combined C/Vitis co-simulation suite, assertions and observed records.
- `rtl_tb.sv`: combined full-queue pin testbench, including sentinels and a temporary input gap; AXI-Lite status reads and cycle-stamped handshakes.
- `matvec_build.py`, `run.tcl`, `run.sh`, `rtl_run.py`: reproducible generation, Vitis and Xsim runs.
- `analyze.py`, `report.py`: measured synthesis/RTL analysis and seven-section report.
- `gen/`, `include/`: generated Waveflow boundaries/serializers; never hand-edit them.

## Reproduce

Use the installed environment and university license server (defaults are in `run.sh`):

```bash
cd ~/hwdesign-work/cmdresp/takehome/matvec
bash ./run.sh --stage all
```

The full run exits nonzero for the observed input-consumption failures, while still running analysis and writing the report. Individual stages:

```bash
bash ./run.sh --stage generate  # scalar/NumPy/protocol verification and Waveflow generation
bash ./run.sh --stage csim
bash ./run.sh --stage synth
bash ./run.sh --stage cosim     # all scenarios in one Vitis invocation
bash ./run.sh --stage rtl       # all full queues in one Xsim invocation; currently fails
bash ./run.sh --stage analyze   # retains measurements, then fails on the contract violation
bash ./run.sh --stage report    # renders retained evidence without pretending tests passed
```

`capture` optionally replays the standard Vitis testbench into a VCD; it is not required because `rtl` directly emits `evidence/rtl.vcd` and per-cycle CSV. The installed Vitis version is 2026.1; the part is xc7z020clg484-1 at 10 ns.

## Evidence and remaining correction

`evidence/interface/` snapshots the generated interface, the source code generator, and the applied/observed interface settings. `set_directive_interface -register_mode off` is recorded but overridden by the generated source pragma. A supported Waveflow boundary-generation change is needed before resynthesis and final verification can pass the no-read-ahead tests. No generated file has been edited to conceal this limitation.

`evidence/run_history.jsonl` tracks prompt/source hashes, executed stages and outcomes. `evidence/manifest.json` hashes all retained evidence and submission sources. `evidence/history/` keeps the original missing-TLAST C failure and the first full-queue RTL failure.
