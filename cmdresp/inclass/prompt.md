# Scale-and-Offset Accelerator

Following Waveflow's stream_inband example, implement a Python golden model, Vitis HLS kernel, and testbench.

Compute `y[i] = a*x[i] + b` in float32, rounding multiplication before addition and disabling fused multiply-add.

Use one input stream for commands/configuration/data and one output stream for responses. Headers and payloads occupy separate TLAST-terminated bursts. AXI-Lite carries only control/status.

Commands:
- CONFIG receives `a,b`, replacing both coefficients for subsequent DATA.
- DATA receives `nsamp` samples and returns a header echoing `tx_id`, followed by ordered results. Zero-length DATA returns only the header.
- END returns normally. CONFIG and END produce no response.

Each activation clears status and starts unconfigured. Errors include malformed header framing, unknown commands, DATA before CONFIG, and early/missing payload TLAST. Validate in that priority order; stop at the first detected error without reading ahead.

On error, record its code and transaction ID, close any output burst, and return without draining input. For DATA framing errors, include the detecting sample's result with output TLAST asserted.

Check the model against hand-computed examples. Test reconfiguration, multiple DATA commands, zero-length DATA, error priority, and every error followed by successful recovery using fresh streams.

Compare Python-model and C-simulation outputs bit for bit, including framing/status. Stop once C simulation passes; no synthesis/co-simulation.

Write results.md with scenario PASS/FAIL results and every point where this prompt was silent or ambiguous, stating the choice made for each.