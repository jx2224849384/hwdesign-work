# Small Matrix-Vector Accelerator

## Task
Following Waveflow's stream_inband example, implement a Python golden model, Vitis HLS kernel, testbench, and reproducible scripts.

Run Python verification, C simulation, synthesis, and RTL co-simulation. Configuration travels through the input stream; AXI-Lite carries only control/status.

## Operation
Compute y[i] = sum(A[i,j] * x[j]) for an R×C matrix, where 1 <= R,C <= 16.

Matrix/vector elements are signed 16-bit integers. Use exact signed 32-bit products and signed 64-bit accumulation/output. No rounding or saturation is needed. Clear accumulators for each vector.

Matrix elements and output rows use row-major order. A configured matrix persists across DATA commands within one activation.

## Protocol
Use 32-bit input/output stream words. Headers and nonempty payloads occupy separate TLAST-terminated bursts.

Each command header contains four unsigned words:
[opcode, tx_id, arg0, arg1].
Assert TLAST only on the fourth word.

Commands:
- CONFIG, opcode 1: arg0=R, arg1=C. Receive R*C matrix elements. Validate dimensions before reading payload. Commit the new matrix and dimensions only after validating the complete payload. Produce no response.
- DATA, opcode 2: arg0=vector length, which must equal C; arg1=0. Receive C vector elements.
- END, opcode 0: both arguments must be zero. No payload or response; return without reading further input.

Input samples use sign-extended 16-bit two's-complement values in 32-bit words. Other sample encodings are outside the host contract.

Buffer and validate the complete DATA payload before emitting anything. Return a three-word response header [2, tx_id, R], with TLAST on its third word. Follow it with one result burst: each signed 64-bit result is serialized as its low 32 bits followed by its high 32 bits. Assert TLAST only on the high word of the final result.

Each activation starts unconfigured and clears status. A successful second CONFIG replaces the entire previous matrix. END is allowed without CONFIG.

## Errors
Expose halted, error, and tx_id status registers, initialized to zero.

| Code | Meaning |
|---|---|
| 1 | Early or missing header TLAST |
| 2 | Unknown opcode |
| 3 | DATA before CONFIG |
| 4 | Invalid command arguments |
| 5 | Early payload TLAST |
| 6 | Missing payload TLAST |

Validate header framing, opcode, configuration availability for DATA, and command arguments in that order. Stop at the first detected error. Invalid arguments include dimensions outside 1..16, DATA length unequal to C, or nonzero reserved arguments.

Detect missing TLAST on the expected final word without reading ahead. Temporary stream emptiness is not an error.

On error, set halted=1, record the error code and offending tx_id, close any started output burst, and return without draining input. For a malformed header, use tx_id=0 if its word was not received.

Emit nothing for a failed command. Previously completed responses remain unchanged. Failed CONFIG commands never commit partial matrices. Recovery requires fresh streams and a new activation.

## Verification
Independently check:
- A=[[1,2],[3,4]], x=[5,6]: y=[17,39].
- A=[[1,-2,3],[-1,0,2]], x=[2,1,-1]: y=[-3,-4].

Also compare against NumPy after converting both operands to int64.

Test 1×1 and 16×16 matrices, rectangular dimensions, zeros, signed extremes, outputs exceeding 32-bit range, repeated DATA, changed dimensions/matrices, and clean state across activations.

Test every error code, header and payload framing failures, competing errors, and END without CONFIG. Follow every error with a successful fresh CONFIG/DATA/END activation.

Compare Python, C simulation, and RTL co-simulation bit for bit: response words, result words, TLAST, and status. Verify unread sentinel words after errors and END.

Use one co-simulation testbench run covering all scenarios, with fresh streams for each activation. Record expected and observed values; test failures must produce a nonzero exit code.

## Performance
Use the reference example's part and clock configuration.

Target estimated clock below 10 ns. A clock-uncertainty warning alone is not failure.

Target DATA latency <=10,000 cycles for 16×16, measured from the first vector-input handshake to the final result-output handshake, with continuous input and no output backpressure. Report throughput as completed vectors per cycle over a documented sequence of repeated DATA commands.

Measure latency/throughput through co-simulation and clock, II, and resources through synthesis. Report missed targets honestly without performance-only redesign. Do not build a Python timing model.

## results.md
Include these seven sections:

1. Interface: command/response serialization, signed-value encoding, status registers, error codes, and validation priority.
2. Design: arithmetic, loops, buffering, and persistent versus per-command state.
3. Targets: required values, measured values, PASS/FAIL, and Source. Report latency, throughput, estimated clock, II, and resources; label unspecified targets "no target".
4. Verification: independent model checks and one row per scenario showing Python/C/RTL agreement and PASS/FAIL. For every error, list expected and observed halted/error/tx_id values, output behavior, unread-input checks, and the following recovery scenario and result.
5. Assumptions: every silent or ambiguous prompt decision and the choice made.
6. Open Items: unresolved issues, failures, and unexecuted checks, or "None".
7. Run History: prompt version, changes, executed checks, and outcomes for each run.

Every measurement and PASS/FAIL in Targets and Verification must have a Source identifying the exact evidence file and relevant test entry, JSON key, or log location. A general bibliography of logs is insufficient.

Retain cited evidence for submission. If required observations are missing, instrument the tests and rerun them. Never substitute expected values for observed values or mark unexecuted checks as passing.

## Revision history
| Version | Change | Reason |
|---|---|---|
| 1 | Initial matrix-vector specification. | Define operation and workflow. |
| 2 | Specify serialization, error codes, and per-test evidence. | Make behavior unambiguous and results independently reviewable. |