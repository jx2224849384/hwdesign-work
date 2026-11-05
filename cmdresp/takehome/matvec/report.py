"""Render the seven required sections with exact per-measurement/per-test evidence."""
from pathlib import Path
import hashlib,json
import scenarios as S
ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'

def load(file): return json.loads((E/file).read_text())
def link(file,label=None): return f'[{label or file}](matvec/evidence/{file})'
def triple(s): return f"{s['halted']}/{s['error']}/{s['tx_id']}"
def pf(x): return 'PASS' if x else 'FAIL'

def write_report():
    py,c,v,rtl=(load(f'{stage}_checks.json') for stage in ('python','csim','cosim','rtl'))
    synth=load('synthesis_metrics.json'); perf=load('performance.json')
    scenarios=S.scenarios(); checks=load('independent.json')
    all_ok=all(d[n]['pass'] for d in (py,c,v,rtl) for n in scenarios)
    history=[json.loads(x) for x in (E/'run_history.jsonl').read_text().splitlines()]
    md='# Small matrix-vector accelerator — results\n\n'
    md+=f"Prompt revision 2; SHA-256 `{hashlib.sha256((ROOT.parent/'prompt.md').read_bytes()).hexdigest()}`. "
    md+=f"**{sum(all(d[n]['pass'] for d in (py,c,v,rtl)) for n in scenarios)}/{len(scenarios)} scenarios pass all functional comparisons.** "
    md+='Vitis HLS 2026.1; reference part `xc7z020clg484-1`, requested clock 10 ns.\n\n'
    md+='## 1. Interface\n\n'
    md+='One 32-bit input AXI-Stream and one 32-bit output AXI-Stream. AXI-Lite carries control/status only. Each header and nonempty payload is a separate TLAST-terminated burst.\n\n'
    md+='| Message | Serialized 32-bit words | TLAST |\n|---|---|---|\n'
    md+='| CONFIG | `[1, tx_id, R, C]`, then `R*C` row-major samples | Header word 4; final sample |\n'
    md+='| DATA | `[2, tx_id, C, 0]`, then `C` samples | Header word 4; final sample |\n'
    md+='| END | `[0, tx_id, 0, 0]` | Word 4 |\n'
    md+='| DATA response | `[2, tx_id, R]`, then results row by row, low 32 bits followed by high 32 bits | Header word 3; high word of last row |\n\n'
    md+='Samples are sign-extended int16 values in signed 32-bit wire fields. Outputs are signed int64 two’s-complement, low word first. All serialization uses Waveflow schemas/array utilities. Concrete serialized examples: '+link('layout.json')+' (`command_example`, `signed_input_example`, `response_example`). CONFIG/END have no response. Failed commands emit nothing; earlier complete responses remain.\n\n'
    md+='Status registers: `halted` (1 bit, offset 0x10), `error` (8 bits, 0x20), `tx_id` (32 bits, 0x30). Control is 0x00; generated control/interrupt and validity registers occupy the other documented offsets. All status clears at activation. Source: [generated AXI-Lite RTL](matvec/evidence/interface/matvec_control_s_axi.v), Address Info block.\n\n'
    md+='| Code | Meaning |\n|---|---|\n| 0 | Success |\n| 1 | Early/missing header TLAST |\n| 2 | Unknown opcode |\n| 3 | DATA before CONFIG |\n| 4 | Invalid arguments |\n| 5 | Early payload TLAST |\n| 6 | Missing payload TLAST |\n\n'
    md+='Validation order is header framing → opcode → DATA configuration availability → arguments → payload framing. Stop on the detecting beat, with no drain; malformed-header tx_id is zero until its word arrives. The implementation attempts to disable input AXIS registers via Tcl, but the generated pragma overrides it; physical read-ahead remains an Open Item. Temporary input emptiness stalls.\n\n'
    md+='## 2. Design\n\n'
    md+='The active matrix and staging matrix each hold at most 256 signed 16-bit elements. A 16-element vector buffer holds each complete DATA payload. CONFIG commits only after validation, replacing dimensions and matrix. DATA validates fully before emitting its header. A sequential row loop runs a pipelined dot-product loop; every product is exact signed 32-bit and is sign-extended into a signed 64-bit accumulator initialized to zero per row/vector. The worst absolute sum is at most 2^34. Matrix/configuration state persists only within an activation. No Python timing model was built.\n\n'
    md+='Source: [kernel body](matvec/matvec_body_impl.tpp), [scalar golden](matvec/matvec.py), [beat protocol model](matvec/protocol_model.py). The original arithmetic architecture was retained; subsequent changes corrected framing and input read-ahead.\n\n'
    md+='## 3. Targets\n\n| Item | Required | Measured | PASS/FAIL | Source |\n|---|---|---|---|---|\n'
    md+=f"| Estimated clock | <10 ns | {synth['estimated_clock_ns']:.3f} ns | {pf(synth['clock_pass'])} | {link('synthesis/matvec_csynth.xml')}, `PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod` |\n"
    md+=f"| 16×16 DATA latency | ≤10,000 cycles | max {perf['maximum_latency_cycles']} cycles | {pf(perf['latency_pass'])} | {link('performance.json')}, `maximum_latency_cycles`, `vectors[0..7]`; exact handshake indices/cycles stored there |\n"
    md+=f"| Throughput | no target | {perf['vectors_per_cycle']:.9f} vectors/cycle = 7/{perf['completion_interval_cycles']} | no target | {link('performance.json')}, `vectors_per_cycle`, `completion_interval_cycles` |\n"
    md+=f"| Full-window throughput | no target | {perf['full_window_vectors_per_cycle']:.9f} vectors/cycle = 8/{perf['full_window_cycles']} | no target | {link('performance.json')}, `full_window_vectors_per_cycle` |\n"
    for loop in synth['loops']:
        md+=f"| {loop['loop']} II | no target | {loop['II']} cycles | no target | [{Path(loop['source']).name}](matvec/{loop['source']}), `{loop['xpath']}` |\n"
    md+='| Top-level command-loop II | no target | not fixed; data-dependent activation length | no target | '+link('synthesis/matvec_csynth.xml')+', `PerformanceEstimates/SummaryOfOverallLatency/Interval-min` = `undef` |\n'
    for resource,value in synth['resources'].items():
        md+=f"| {resource} | no target | {value} | no target | {link('synthesis/matvec_csynth.xml')}, `AreaEstimates/Resources/{resource}` |\n"
    md+=f"\nDefault clock uncertainty is {synth['clock_uncertainty_ns']} ns (same XML, `UserAssignments/ClockUncertainty`). Synthesis estimates are not post-route timing.\n\n"
    md+='The performance sequence is eight consecutive 16×16 DATA commands, IDs 1000–1007, under one CONFIG. Latency is the elapsed edge difference from the first vector beat to the final result high-word handshake. Throughput is seven completion intervals from the first completion through the eighth, excluding CONFIG and initial fill. Full-window throughput includes the first vector’s latency. The table below records each observation; continuous input and ready output are verified from recorded pin values, not assumed.\n\n'
    md+='| DATA tx_id | First vector cycle | Final result cycle | Latency | Input continuous | Output no backpressure | Source |\n|---|---|---|---|---|---|---|\n'
    for i,r in enumerate(perf['vectors']):
        md+=f"| {r['tx_id']} | {r['first_vector_handshake_cycle']} | {r['final_result_handshake_cycle']} | {r['latency_cycles']} | {r['continuous_input']} | {r['no_output_backpressure']} | {link('performance.json')}, `vectors[{i}]`; input/output event indices therein, {link('rtl/performance_16x16/cycles.csv','flow control')} |\n"
    md+='\n## 4. Verification\n\n'
    md+='The scalar Python arithmetic is checked independently against both hand examples and NumPy after both operands are converted to int64. Protocol expectations come from intent fixtures using NumPy, independently of the beat-parsing golden.\n\n'
    md+='| Check | Expected | Observed | Result | Source |\n|---|---|---|---|---|\n'
    for name in ('hand_17_39','hand_negative'):
        r=checks[name]
        md+=f"| {name} | {r['expected']} | {r['observed']} | {pf(r['pass'])} | {link('independent.json')}, `{name}` |\n"
    md+=f"| NumPy int64 @, every R,C in 1..16 | 256 exact comparisons | {sum(checks[f'numpy_{r}x{c}']['pass'] for r in range(1,17) for c in range(1,17))} passing | {pf(all(checks[f'numpy_{r}x{c}']['pass'] for r in range(1,17) for c in range(1,17)))} | {link('independent.json')}, all `numpy_RxC` entries for R,C=1..16; each has expected/observed vectors |\n"
    md+='\nP = Python beat model; C = C simulation; V = standard Vitis C/RTL co-simulation; R = supplemental full-queue pin-level RTL co-simulation. Every row compares exact response/result words, TLAST, status, consumed counts and unread suffixes. Vitis’s adapter omits unread words from RTL replay; therefore physical sentinel claims use R, not V. The R testbench keeps queued input VALID through at least 20 cycles after completion and checks for extra acceptance; this check currently fails because of input adapter prefetch. Source entries include expected and observed data, not only booleans.\n\n'
    md+='| Scenario | P | C | V | R / overall agreement | Source (exact key in each JSON) |\n|---|---|---|---|---|---|\n'
    for n in scenarios:
        md+=f"| {n} | {pf(py[n]['pass'])} | {pf(c[n]['pass'])} | {pf(v[n]['pass'])} | {pf(rtl[n]['pass'] and all(d[n]['pass'] for d in (py,c,v)))} | {link('python_checks.json','P')}, {link('csim_checks.json','C')}, {link('cosim_checks.json','V')}, {link('rtl_checks.json','R')}: `{n}` |\n"
    md+='\nFor every error, statuses below are `halted/error/tx_id`; “observed” lists P, C, V, R in that order. Output counts include response and result words. “Unread” compares the entire suffix word/TLAST sequence; counts alone are not the acceptance criterion. Each R entry links to its actual pin-event files and AXI-Lite status recording.\n\n'
    md+='| Error scenario | Expected status | Observed P; C; V; R | Output expected / R observed | Unread expected / R observed | Following recovery | Source |\n|---|---|---|---|---|---|---|\n'
    for n,sc in scenarios.items():
        if not sc.status['halted']: continue
        r=rtl[n]
        statuses='; '.join(triple(d[n]['observed_status']) for d in (py,c,v,rtl))
        recover=sc.recovery
        rok=all(d[recover]['pass'] for d in (py,c,v,rtl))
        md+=f"| {n} | {triple(sc.status)} | {statuses} | {len(r['expected_output'])} / {len(r['observed_output'])}; {pf(r['checks']['response_bits_tlast'])} | {len(r['expected_unread'])} / {len(r['observed_unread'])}; {pf(r['checks']['unread_suffix'] and r['checks']['sentinel_present_and_stalled'])} | {recover}: {pf(rok)} | {link('rtl_checks.json','R')}: `{n}` (`checks`, `sources`, expected/observed fields); P/C/V keys as above, recovery key `{recover}` |\n"
    md+='\nEvery zero-output failed command has no response header. The two `failed_*_after_success`/reconfiguration cases retain only earlier completed output, verified word-for-word. The END sentinel checks also fail at the pins, as shown by `checks.unread_suffix` and `checks.sentinel_present_and_stalled` for each successful row in `rtl_checks.json`. `example_negative` additionally inserts a four-cycle producer gap, visible in its `cycles.csv`; the kernel stalls and completes correctly. The R harness resets the physical path after each failed check to permit subsequent diagnostics; these diagnostic recoveries are not marked passing. The standard Vitis testbench retains status between calls, but its input replay limitation prevents a full-queue recovery claim.\n\n'
    md+='Both C++ and pin-level testbenches fail their invocation on mismatches; the Python runner additionally checks observed RTL statuses because Xsim can exit zero after `$fatal`. Standard Vitis summary: '+link('cosim.log')+', line containing `C/RTL co-simulation finished: PASS`; full-queue summary: '+link('rtl_sim.log')+', line `PIN_RTL_SUMMARY tests=85 failures=85`.\n\n'
    md+='## 5. Assumptions\n\n'+(ROOT/'assumptions.md').read_text()+'\n'
    md+='## 6. Open Items\n\n'
    issues=[]
    if not all_ok: issues.append('The full-queue pin-level RTL check fails: the generated AXIS input adapter accepts two extra words after each activation stopping point. All 85 scenarios fail exact consumed-count/unread-suffix checks, despite matching response words and status. Sources: `evidence/rtl_checks.json`, each scenario’s `expected_consumed`, `observed_consumed`, `checks`; actual handshakes in each `sources` entry. This violates the no-read-ahead requirement, including following recovery activations.')
    if not all_ok: issues.append('Waveflow’s generated boundary hardcodes `#pragma HLS INTERFACE axis port=s_in` with default registration and exposes no register-mode option. The Tcl off directive was applied but synthesis retained both-mode registers. No generated files were edited. A framework/code-generation change is needed to express the required interface and then rerun synthesis, standard co-simulation, and full-queue checks. Sources: `evidence/synth.log`, interface-mode lines; `evidence/interface/solution1_data.json`, `DirectiveTcl` and interface `register_mode`; `evidence/interface/generated_matvec.cpp` and `evidence/interface/waveflow_hwgen_source.py::kernel_signature`.')
    if not synth['clock_pass']: issues.append('Estimated clock target missed; no performance-only redesign performed.')
    if not perf['latency_pass']: issues.append('Latency target or required flow-control conditions not met; see performance.json.')
    md+=('\n'.join('- '+x for x in issues) if issues else 'None. All required checks executed and observed targets met.')+'\n\n'
    md+='## 7. Run History\n\n'
    md+='Prompt revision 2 was used throughout. Machine-readable history retains the prompt hash, source hashes, exact stages, elapsed times, outcomes and exceptions: '+link('run_history.jsonl')+'. No performance-only architecture iteration was performed.\n\n'
    md+='| History entry (1-based line) | Stage | Outcome | Seconds | Evidence / change |\n|---|---|---|---|---|\n'
    for i,h in enumerate(history,1):
        detail=h.get('error','Completed stage; detailed outputs retained under evidence/.')
        md+=f"| {i} | {h['stage']} | {pf(h['pass'])} | {h['elapsed_seconds']:.2f} | {link('run_history.jsonl')}, line {i}; {detail.replace('|','/')} |\n"
    md+='\n'+(ROOT/'implementation_notes.md').read_text().replace('# Implementation and integration notes\n','')
    md+='\nReproduce from the project directory with `bash ./run.sh --stage all`. It uses the existing Waveflow Python environment and installed Xilinx tools; license-server access is needed. Individual stages are documented in [README.md](matvec/README.md). All cited evidence is retained for submission.\n'
    (ROOT.parent/'results.md').write_text(md)
    print('Report written:',ROOT.parent/'results.md')
if __name__=='__main__': write_report()
