# Small matrix-vector accelerator

Implements `../prompt.md` revision 3 using the Waveflow `stream_inband` architecture.
The final report is [../results.md](../results.md). Retained observations are under
`evidence/`; the source prompt is unchanged.

Run all checks:

```bash
bash ./run.sh --through summary
```

Or run individual stages in dependency order:

```bash
bash ./run.sh --stage generate # independent arithmetic, scenarios, Python, code generation
bash ./run.sh --stage csim
bash ./run.sh --stage synth
bash ./run.sh --stage cosim    # one combined 126-activation C++ testbench execution
bash ./run.sh --stage rtl      # one combined pin-level suite with explicit reset recovery
bash ./run.sh --stage analyze
bash ./run.sh --stage report
```

`--stage all` is equivalent to `--through summary`. All functional mismatches,
missing evidence and simulator failures yield nonzero exit status. Performance
misses are reported without automatic redesign. Test expectations are never
replaced by observed outputs. History is appended and earlier observations
are archived on reruns.

Dependencies: Python 3.12 with Waveflow and NumPy, Vitis HLS/Vivado 2026.1,
and access to the configured Xilinx license server. Defaults use this workspace's
existing Python environment and `/eda/xilinx`. Override `MATVEC_PYTHON`,
`WAVEFLOW_VITIS_PATH`, `MATVEC_VIVADO_BIN`, and `XILINXD_LICENSE_FILE` as needed.
The synthesis part is `xc7z020clg484-1`; clock is 10 ns with default uncertainty.
Restricted network environments must permit license-server access.

The kernel boundary and serializers in `gen/` and `include/` are generated.
Do not edit them. `interface_codegen.py` is a maintained, project-local extension
of the Waveflow signature emitter; `MatvecAccel.axis_register_modes` specifies
unregistered input, verified again in synthesis and at RTL pins. No modification
to the installed Waveflow package or generated RTL is required.

Source map:

- `matvec.py`: schemas, scalar integer golden, module/interface definition.
- `protocol_model.py`: untimed beat parser and functional model.
- `scenarios.py`: independent intent fixtures, NumPy oracle, strict checker.
- `matvec_body_impl.tpp`: synthesizable computation and command processing.
- `matvec_tb.cpp`: combined C simulation / RTL co-simulation testbench.
- `rtl_tb.sv`, `rtl_run.py`: AXI-Lite control and pin-level stream tests.
- `analyze.py`, `report.py`: observed timing, synthesis metrics, and report.
- `matvec_build.py`, `run.tcl`, `run.sh`: reproducible orchestration.

`evidence/rtl/<scenario>/` contains every accepted beat with its cycle, per-cycle
VALID/READY/TLAST/byte strobes, status read over AXI-Lite, and untouched suffix.
`evidence/vectors/<scenario>/` contains input/expected/Python/C/RTL bundles and
status. `evidence/synthesized_rtl/` retains the unmodified synthesized design.
`evidence/history/previous_*` preserves the prior revision-2 report and run records;
those historical failures are distinct from current evidence.
