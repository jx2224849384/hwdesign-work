"""Render exactly the seven requested sections from retained observations."""
from pathlib import Path
import hashlib, json
from datetime import datetime
from zoneinfo import ZoneInfo
import scenarios as S
ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'
def load(file): return json.loads((E/file).read_text())
def link(file,label=None): return f'[{label or file}](accelerator/evidence/{file})'
def triple(s): return '/'.join(str(s[k]) for k in ('halted','error','tx_id'))
def pf(value): return 'PASS' if value else 'FAIL'

def write_report():
    stages={s:load(f'{s}_checks.json') for s in ('python','csim','cosim','rtl')}
    py,c,v,rtl=(stages[s] for s in stages)
    synth=load('synthesis_metrics.json'); perf=load('performance.json')
    tests=S.scenarios(); independent=load('independent.json'); negative=load('negative_controls.json')
    histories=[json.loads(x) for x in (E/'run_history.jsonl').read_text().splitlines()]
    all_ok=all(d[n]['pass'] for d in stages.values() for n in tests)
    count=sum(all(d[n]['pass'] for d in stages.values()) for n in tests)
    m=['### Interface\n']
    def add(text): m.append(text+'\n')
    add(f"Small matrix-vector accelerator, prompt revision **3**, SHA-256 `{hashlib.sha256((ROOT.parent/'prompt.md').read_bytes()).hexdigest()}`. "
        f"Observed cross-layer result: **{count}/{len(tests)} scenarios {pf(all_ok)}**. Sources: each scenario key in "
        +', '.join(link(f'{s}_checks.json',s) for s in stages)+'.')
    add('One 32-bit input AXI-Stream and one 32-bit output AXI-Stream; AXI-Lite carries only control/status. Every header and nonempty payload is a separate TLAST-terminated burst. All byte-valid strobes are asserted.')
    add('| Command / response | 32-bit words | TLAST |\n|---|---|---|\n'
        '| CONFIG | `[1, tx_id, R, C]`, then R×C row-major elements | Header word 4; final matrix element |\n'
        '| DATA | `[2, tx_id, C, 0]`, then C elements | Header word 4; final vector element |\n'
        '| END | `[0, tx_id, 0, 0]` | Header word 4 |\n'
        '| Successful DATA response | `[2, tx_id, R]`, then R signed 64-bit results | Header word 3; high word of final result |')
    add('Each sample is a signed int16 two’s-complement value sign-extended to 32 bits. Each result is serialized low 32 bits first, then high 32 bits. CONFIG and END have no response. Repeated uint32 IDs are echoed unchanged. Concrete serialized examples: '+link('layout.json')+', keys `command_example`, `signed_input_example`, `response_example`; [layout.md](accelerator/layout.md).')
    add('All status registers are unsigned **32-bit**: `halted` at 0x10, `error` at 0x20, `tx_id` at 0x30; control at 0x00. Companion validity/interrupt registers are the standard HLS control interface. Status initializes to 0/0/0 at every activation and stays zero on normal completion. Generated address/width evidence: '+link('synthesized_rtl/matvec_control_s_axi.v')+', `Address Info` and `int_halted/int_error/int_tx_id` declarations.')
    add('| Error | Meaning |\n|---|---|\n| 1 | Early or missing header TLAST |\n| 2 | Unknown opcode |\n| 3 | DATA before CONFIG |\n| 4 | Invalid dimensions, DATA length, or reserved argument |\n| 5 | Early payload TLAST |\n| 6 | Missing payload TLAST |')
    add('Validation priority is header framing → opcode → DATA configuration availability → arguments → payload framing. The first detected failure sets halted=1, error, and offending ID (zero when its header word has not arrived), then returns without draining. No response is emitted for a failed command; earlier responses remain complete. Temporary emptiness waits. END stops at its fourth word; errors stop at the detecting word, including at the **external** input handshake. No later word may be accepted through idle before another activation.')
    add('### Design\n')
    add('The scalar Python golden and C++ body multiply signed 16-bit operands into exact signed 32-bit products, sign-extend each into a signed 64-bit accumulator, and clear the accumulator per row/vector. The largest possible magnitude is 16×2³⁰=2³⁴. A row loop contains a pipelined dot-product loop. No rounding or saturation occurs.')
    add('The active matrix and a separate staging buffer each hold 256 int16 values; the vector buffer holds 16. CONFIG validates the entire staging payload before copying it and committing dimensions. DATA buffers and validates its entire payload before the first response word. Local configured state starts false at each activation. No errors remain to be detected during response emission, so every started output burst closes before any later command can fail.')
    add('The maintained [interface_codegen.py](accelerator/interface_codegen.py) extends Waveflow’s interface signature emitter before generation, reading `axis_register_modes` from [matvec.py](accelerator/matvec.py). It emits `register_mode=off` on s_in. The installed Waveflow package and generated files are never edited. Header/payload/command loops explicitly disable pipelining to prevent reads ahead of validation. Output registration remains enabled. Synthesis confirms unregistered input: '+link('input_interface.json')+', `no_registered_input` and `binding_lines`; actual RTL handshake evidence is reported separately below. AMD defines the mode in [UG1399](https://docs.amd.com/r/2025.1-English/ug1399-vitis-hls/pragma-HLS-interface).')
    add('Wire encoding uses generated Waveflow schemas and array serializers. The installed int64 stream helper discards TLAST, so the body uses the generated array serializer followed by the supported stream word writer with explicit burst boundaries. This does not manually pack result bits. Sources: [kernel](accelerator/matvec_body_impl.tpp), [golden](accelerator/matvec.py), [protocol model](accelerator/protocol_model.py), [testbench](accelerator/matvec_tb.cpp). No Python timing model was built.')
    add('### Targets\n')
    add('| Item | Required | Measured | Result | Exact source |\n|---|---|---|---|---|')
    add(f"| Estimated clock | <10 ns | {synth['estimated_clock_ns']:.3f} ns | {pf(synth['clock_pass'])} | {link('synthesis/matvec_csynth.xml')}: `PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod` |")
    add(f"| 16×16 DATA latency, inclusive | ≤10,000 cycles | max {perf['maximum_latency_cycles']} cycles | {pf(perf['latency_pass'])} | {link('performance.json')}: `maximum_latency_cycles`, `latency_pass`, `vectors[0..7]` |")
    add(f"| Throughput, N={perf['N']} consecutive vectors | no target | {perf['N']}/{perf['elapsed_cycles']} = {perf['vectors_per_cycle']:.9f} vectors/cycle | no target | {link('performance.json')}: `N`, `elapsed_cycles`, `vectors_per_cycle` |")
    for loop in synth['loops']:
        add(f"| {loop['loop']} II | no target | {loop['II']} cycles | no target | [{Path(loop['source']).name}](accelerator/{loop['source']}): `{loop['xpath']}` |")
    add('| Top-level activation II | no target | variable; not a fixed vector II | no target | '+link('synthesis/matvec_csynth.xml')+': `PerformanceEstimates/SummaryOfOverallLatency/Interval-min` |')
    for resource,value in synth['resources'].items():
        add(f"| {resource} | no target | {value} | no target | {link('synthesis/matvec_csynth.xml')}: `AreaEstimates/Resources/{resource}` |")
    add(f"Reference part `xc7z020clg484-1`, requested clock {synth['requested_clock_ns']} ns, default uncertainty {synth['clock_uncertainty_ns']} ns; source: same synthesis XML, `UserAssignments`. Tools: Vitis HLS/Vivado 2026.1 (`evidence/synth.log`, version banner). Clock is a synthesis estimate, not routed timing.")
    add('Timing is measured at RTL pins. Latency is final result handshake cycle minus first vector-input handshake cycle **plus one**. Throughput is N divided by the same inclusive window spanning all eight consecutive DATA commands (IDs 1000–1007); initial CONFIG is excluded. Continuous input and no output backpressure are checked over the entire measurement window: '+link('performance.json')+', `continuous_input`, `no_output_backpressure`.')
    add('| DATA ID | First vector handshake | Final result handshake | Inclusive latency | Exact source |\n|---|---|---|---|---|')
    for i,r in enumerate(perf['vectors']):
        add(f"| {r['tx_id']} | {r['first_vector_handshake_cycle']} | {r['final_result_handshake_cycle']} | {r['latency_cycles']} | {link('performance.json')}: `vectors[{i}]`, including exact event indices into `source_input` and `source_output` files |")
    add('### Verification\n')
    add('Expected protocol responses are built from explicit scenario intents and NumPy int64 matrix multiplication, independently of the beat parser and scalar golden. Both operands are converted to int64 before NumPy multiplication. Every scenario uses fresh streams and a separate kernel activation within **one combined C/RTL co-simulation execution**.')
    add('| Independent arithmetic check | Expected | Observed | Result | Exact source |\n|---|---|---|---|---|')
    for name in ('hand_17_39','hand_negative'):
        r=independent[name]
        add(f"| {name} | {r['expected']} | {r['observed']} | {pf(r['pass'])} | {link('independent.json')}: `{name}` |")
    np_keys=[k for k in independent if k.startswith('numpy_')]
    add(f"| All dimensions R,C=1..16 | 256 NumPy int64 comparisons | {sum(independent[k]['pass'] for k in np_keys)}/256 | {pf(all(independent[k]['pass'] for k in np_keys))} | {link('independent.json')}: all `numpy_RxC` entries, expected and observed vectors |")
    add('Checker negative controls: '+link('negative_controls.json')+', exact keys `wrong_result_bit`, `missing_output_tlast`, `extra_input_accepted`, `uncleared_status`; each deliberately invalid observation has `pass=false` and identifies the failed comparison. These use the same checker as the Python/C/RTL bundle comparisons.')
    add('P = Python functional model; C = C simulation; V = standard Vitis RTL co-simulation; R = separate pin-level RTL testbench. P/C/V compare response/result bits, TLAST, status, accepted count and unread suffix. The Vitis adapter trims unread input from RTL replay, so its C-side unread check is **not physical stopping evidence**. R drives the full queue with sentinel words, keeps VALID after completion, and compares actual accepted input and output handshakes, byte strobes, status via AXI-Lite, and the complete untouched suffix. Each R entry also checks no input acceptance during pre-start idle and at least 20 sentinel-stalled cycles after completion.')
    add('| Scenario / coverage | P | C | V | R | Exact evidence keys |\n|---|---|---|---|---|---|')
    for name,sc in tests.items():
        source=', '.join(link(f'{stage}_checks.json',label) for stage,label in zip(stages,'PCVR'))
        add(f"| {name}: {sc.purpose} | {pf(py[name]['pass'])} | {pf(c[name]['pass'])} | {pf(v[name]['pass'])} | {pf(rtl[name]['pass'])} | {source}: `{name}` |")
    add('For every error below, status triples are halted/error/tx_id. Observations are listed in P/C/V/R order. Accepted counts are expected / observed P,C,V,R. Output and suffix columns give expected/observed word counts at pins and a full word/TLAST comparison verdict, not just a count check. Each recovery is the **immediately following** activation and asserts reset for eight clock cycles before CONFIG/DATA/END. Exact per-cycle files are linked by the `sources` object in each R entry.')
    add('| Error scenario | Expected status | Observed P; C; V; R | Accepted counts | Output words E/R | Unread suffix words E/R | Subsequent recovery | Exact source |\n|---|---|---|---|---|---|---|---|')
    for name,sc in tests.items():
        if not sc.status['halted']: continue
        r=rtl[name]; recovery=sc.recovery
        statuses='; '.join(triple(d[name]['observed_status']) for d in stages.values())
        counts=f"{sc.consumed} / "+','.join(str(d[name]['observed_consumed']) for d in stages.values())
        out=f"{len(r['expected_output'])}/{len(r['observed_output'])} {pf(r['checks']['response_bits_tlast'])}"
        left=f"{len(r['expected_unread'])}/{len(r['observed_unread'])} {pf(r['checks']['unread_suffix'])}"
        recovery_ok=all(d[recovery]['pass'] for d in stages.values())
        add(f"| {name} | {triple(sc.status)} | {statuses} | {counts} | {out} | {left} | {recovery}: {pf(recovery_ok)}, reset={rtl[recovery]['reset_cycles_before']} clocks | {link('rtl_checks.json','R')}: `{name}` and `{recovery}`; P/C/V same keys in preceding table |")
    add('Zero-output errors emit no response header. `failed_reconfiguration` and `failed_data_after_success` preserve exactly the earlier completed response. `activation_unconfigured` follows successful activations without reset and tests that CONFIG does not survive. `source_gaps` injects pauses in a header and vector payload; `output_backpressure` checks a stalled response stays stable. Exact observations: '+link('rtl_checks.json')+', corresponding entries, `checks`, `sources.cycles.csv`; '+link('rtl_sim.log')+', `PIN_RTL_SUMMARY` line. Standard co-simulation: '+link('cosim_report/matvec_cosim.rpt')+', Verilog result; '+link('cosim.log')+', `C/RTL co-simulation finished` line. All test failures produce nonzero runner exit status, including Xsim `$fatal` failures checked by the Python wrapper.')
    add('### Assumptions\n')
    add((ROOT/'assumptions.md').read_text().strip())
    add('### Open Items\n')
    issues=[]
    if not all_ok: issues.append('Functional comparisons failed; see the exact scenario entries above. Implementation is not accepted.')
    if not synth['clock_pass']: issues.append('Estimated clock target missed. No performance-only redesign was performed.')
    if not perf['latency_pass']: issues.append('Latency target missed. No performance-only redesign was performed.')
    add('\n'.join('- '+x for x in issues) if issues else 'None. All required functional, physical stopping, recovery, and performance checks completed successfully; sources are specified above.')
    add('### Run History\n')
    add('The earlier revision-2 records are preserved unchanged: '+link('history/previous_results.md')+', '+link('history/previous_run_history.jsonl')+' and '+link('history/previous_commit.txt')+'. They document the prior two-extra-handshake failure and are not used to claim success for this implementation.')
    add('Revision-3 implementation changes: '+(ROOT/'implementation_notes.md').read_text().strip())
    add('The scaffold Python run passed before adaptation: '+link('history/scaffold_python.log')+', `py_sim` entry. The first revision-3 C-simulation attempt failed before compilation because license access was unavailable in the sandbox; the retry with license-server network access succeeded. No functional assertion was weakened.')
    add('| History line | Started (America/New_York) | Stage | Outcome | Seconds | Exact source / observation |\n|---|---|---|---|---|---|')
    for i,h in enumerate(histories,1):
        stamp=datetime.fromtimestamp(h['started_unix'],ZoneInfo('America/New_York')).isoformat()
        detail=h.get('error','Completed; stage observations retained under evidence.').replace('|','/')
        add(f"| {i} | {stamp} | {h['stage']} | {pf(h['pass'])} | {h['elapsed_seconds']:.2f} | {link('run_history.jsonl')}, line {i}: {detail} |")
    add('Every machine history record includes prompt revision/hash and maintained source hashes. Reproduce with `bash accelerator/run.sh --through summary` from takehome (or `bash ./run.sh --stage all` from accelerator). Individual stages and environment overrides are documented in [README.md](accelerator/README.md). No commit or push was performed.')
    # Adjacent table rows must stay adjacent in Markdown; paragraphs remain separated.
    text='\n'.join(m)
    text=text.replace('|\n\n|','|\n|')
    (ROOT.parent/'results.md').write_text(text)
    print('Report written:',ROOT.parent/'results.md')

if __name__=='__main__': write_report()
