# Small Matrix-Vector Accelerator

## Task
Implement a Python golden model, Vitis HLS kernel, testbench, and reproducible scripts following Waveflow's stream_inband example.

Complete Python verification, C simulation, synthesis, and RTL co-simulation. Computational parameters must travel through the input stream; AXI-Lite carries only control and status.

## Operation
Compute:

y[i] = sum(A[i,j] * x[j], j=0,...,C-1)

Support 1 <= R,C <= 16. Matrix and vector elements are signed 16-bit integers. Use exact signed 32-bit products, sign-extended into signed 64-bit accumulators. Outputs are signed 64-bit integers. No rounding or saturation is required.

Receive matrix elements in row-major order and output results in increasing row order. Clear accumulators for each vector. Reuse the configured matrix across DATA commands within one activation.

## Protocol
Use 32-bit input and output stream words. Each header and each nonempty payload forms a separate TLAST-terminated burst. Set all byte-valid strobes when present.

Each command header contains four unsigned words:
[opcode, tx_id, arg0, arg1]

Assert header TLAST only on the fourth word.

Commands:
- CONFIG, opcode 1: arg0=R, arg1=C. Receive R*C matrix elements. Validate dimensions before reading the payload. Commit the complete matrix and dimensions only after validating the entire payload. Produce no response.
- DATA, opcode 2: arg0=C, arg1=0. Receive C vector elements. Require a successful CONFIG earlier in this activation.
- END, opcode 0: arg0=0, arg1=0. No payload or response. Return normally.

Input samples are signed 16-bit two's-complement values sign-extended into 32-bit words. Other sample encodings are outside the host contract.

Buffer and validate the entire DATA payload before producing output. Emit a three-word response header [2, tx_id, R], with TLAST on its third word. Follow it with one result burst. Serialize each signed 64-bit result as its low 32 bits followed by its high 32 bits. Assert TLAST only on the high word of the final result.

Each activation clears status and starts unconfigured. A second successful CONFIG replaces the entire matrix and dimensions. END is valid without CONFIG. Transaction IDs may repeat and must be echoed unchanged.

## Errors
Expose unsigned 32-bit status registers halted, error, and tx_id. Initialize all three to zero at activation start. Normal completion leaves them zero.

| Code | Meaning |
|---|---|
| 1 | Early or missing header TLAST |
| 2 | Unknown opcode |
| 3 | DATA before CONFIG |
| 4 | Invalid command arguments |
| 5 | Early payload TLAST |
| 6 | Missing payload TLAST |

Validate header framing, opcode, configuration availability for DATA, and command arguments in that order. Stop at the first detected failure.

Invalid arguments include dimensions outside 1..16, DATA length unequal to C, or nonzero reserved arguments.

Early TLAST occurs before the expected final word. Missing TLAST is detected when the expected final word arrives without TLAST. Do not read another word to search for TLAST. Temporary input emptiness is not a framing error.

On error, set halted=1, record the error code and offending tx_id, close any started output burst, and return without draining input. For a malformed header, record tx_id=0 if its word has not been received.

Emit no response for the failed command. Preserve earlier completed responses. Never commit a partial CONFIG.

## Physical AXI-Stream stopping behavior
Enforce stopping at the external input interface, not merely at C++ stream reads. A word is accepted when TVALID and TREADY are both asserted at a clock edge.

For END, the last accepted word is the final END-header word. For an error, it is the word that makes the error detectable under the validation order above.

No later word may be accepted during that activation or while idle afterward before a new activation. Interface buffers or prefetch must not accept words beyond this boundary.

Enforce this through maintained source or interface-generation configuration. Do not rely on manual edits to generated RTL.

Recovery resets the stream path and starts a fresh activation with new CONFIG. Model that reset explicitly in pin-level tests.

## Verification
Independently check:
- A=[[1,2],[3,4]], x=[5,6]: y=[17,39].
- A=[[1,-2,3],[-1,0,2]], x=[2,1,-1]: y=[-3,-4].

Also compare against NumPy after converting operands to int64.

Test minimum and maximum dimensions, rectangular matrices, zeros, signed extremes, results exceeding signed 32-bit range, repeated DATA, reconfiguration, and cleared state across activations.

Exercise every error code, early/missing header and payload TLAST, competing errors, and END without CONFIG. Follow every error with a successful fresh CONFIG/DATA/END activation.

Compare Python, C simulation, and RTL co-simulation bit for bit, including response words, results, TLAST, and status.

Use one co-simulation testbench execution to cover all scenarios in sequence, with a separate kernel activation and fresh streams for each activation.

Additionally verify external AXI handshakes with continuously available input and sentinel words beyond each stopping point. Check accepted-word counts, untouched suffixes, output framing, status, and recovery. Passing standard co-simulation does not override a failing pin-level check.

Record actual observations. Failures must produce a nonzero test exit status. Fix functional failures and rerun affected checks; do not weaken assertions or remove failing scenarios.

## Performance
Use the reference example's part and clock configuration.

Target estimated clock below 10 ns. A clock-uncertainty warning alone is not failure.

Target DATA latency <=10,000 cycles for 16×16, measured from the first vector-input handshake to the final result-output handshake, inclusive, with continuous input and no output backpressure.

Report throughput as N completed vectors divided by elapsed cycles from the first vector-input handshake to the final result-output handshake over N consecutive DATA commands. State N and exclude initial CONFIG.

Measure latency and throughput through RTL simulation; report estimated clock, II, and resources from synthesis. Report missed performance targets honestly without performance-only redesign. Do not build a Python timing model.

## results.md
Include exactly these seven top-level sections:

### Interface
Document command/response layouts, signed-value packing, status registers, error codes, validation priority, and external stopping behavior.

### Design
Describe arithmetic, loops, buffering, state, and how the interface prevents acceptance beyond a stopping point.

### Targets
For each target, report required and measured values, PASS/FAIL, and Source. Report latency, throughput, estimated clock, II, and resources; mark unspecified targets "no target".

### Verification
Include independent arithmetic checks and a table covering every scenario.

Report Python/C/RTL comparisons and pin-level checks separately. For each error, show expected and observed halted/error/tx_id values, output behavior, accepted-input counts, unread suffixes, and the subsequent recovery scenario and result.

### Assumptions
List every silent or ambiguous specification point and the choice made. Do not treat an explicit requirement as optional.

### Open Items
List unresolved issues, failed checks, and unexecuted checks. Write "None" only when supported by completed verification.

### Run History
Record the prompt version, implementation changes, executed checks, and outcomes for each actual run. Preserve earlier run records.

Every measurement and PASS/FAIL in Targets and Verification must identify an exact evidence file and relevant test entry, JSON key, or log location. Retain those files for submission. A general list of logs is insufficient.

If observations are missing, instrument and rerun the tests. Never substitute expected values for observed values.

Do not automatically commit or push. Do not modify this specification.

## Revision history
| Version | Change | Reason |
|---|---|---|
| 1 | Initial matrix-vector specification. | Define computation and verification scope. |
| 2 | Clarified serialization, error codes, and evidence requirements before implementation. | Preparatory specification update, not a response to an implementation run. |
| 3 | Explicitly defined external handshake stopping and required pin-level evidence. | The preceding run's results.md Open Items reported two extra accepted input words beyond stopping points and failures in all 85 pin-level scenarios. |