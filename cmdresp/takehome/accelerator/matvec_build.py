"""Reproducible staged build; evidence and run history are retained."""
import argparse, hashlib, json, os, shutil, subprocess, time
from pathlib import Path
import numpy as np
from waveflow.build.build import BuildConfig, BuildDag
from waveflow.build.hwcodegen_steps import HlsCodegenStep
from waveflow.build.build import SourceStep
from waveflow.build.streamutils import StreamUtilsStep
from waveflow.hw.arrayutils import ArrayUtilsStep
from waveflow.hw.dataschema import DataSchemaStep
from waveflow.utils.burst_io import write_bursts, read_bursts
from waveflow.toolchain import toolchain
from matvec import SCHEMAS, I32, I64, MatvecAccel
from protocol_model import matvec_stream_model
import scenarios as S
ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2)+'\n')

def generate():
    tests=S.scenarios()
    dump(E/'independent.json',S.independent_checks())
    dump(E/'negative_controls.json',S.negative_controls())
    report={}
    for name,sc in tests.items():
        d=E/'vectors'/name
        write_bursts(sc.stimulus,d/'in')
        write_bursts(sc.expected,d/'expected')
        left=S.beats(sc.stimulus)[sc.consumed:]
        write_bursts(S.from_beats(left),d/'expected/unread')
        dump(d/'expected/status.json',{**sc.status,'consumed':sc.consumed})
        (d/'expected.txt').write_text(f"{sc.status['halted']} {sc.status['error']} {sc.status['tx_id']} {sc.consumed}\n")
        res=matvec_stream_model(sc.stimulus)
        write_bursts(res['out'],d/'python')
        dump(d/'python/status.json',{**res['status'],'consumed':res['consumed']})
        write_bursts(S.from_beats(S.beats(sc.stimulus)[res['consumed']:]),d/'python/unread')
        verdict=S.compare_observation(sc,res['out'],res['status'],res['consumed'],
            S.from_beats(S.beats(sc.stimulus)[res['consumed']:]))
        ok=verdict['pass']
        report[name]={'pass':ok,'expected_status':sc.status,'observed_status':res['status'],
                      'expected_consumed':sc.consumed,'observed_consumed':res['consumed'],
                      'expected_output':S.beats(sc.expected),'observed_output':S.beats(res['out']),
                      'expected_unread':left,'observed_unread':S.beats(sc.stimulus)[res['consumed']:],
                      'recovery':sc.recovery,'purpose':sc.purpose,'vectors':sc.vectors}
        for stage in ('csim','cosim'):
            (d/stage/'unread').mkdir(parents=True,exist_ok=True)
        print('python',name,'PASS' if ok else 'FAIL',flush=True)
    (E/'vectors/scenarios.txt').write_text('\n'.join(tests)+'\n')
    dump(E/'python_checks.json',report)
    assert all(x['pass'] for x in report.values())
    dag=BuildDag()
    dag.add(StreamUtilsStep(output_dir='include'))
    for cls in SCHEMAS:
        dag.add(DataSchemaStep(cls,word_bw_supported=[32],include_dir='include'))
    for cls in (I32,I64): dag.add(ArrayUtilsStep(cls,[32]))
    dag.add(SourceStep(artifact='source',path=ROOT/'matvec.py'))
    dag.add(HlsCodegenStep(name='kernel',comp_class=MatvecAccel,source_artifact='source',output_dir='gen',impl_dir='.'))
    from interface_codegen import axis_register_configuration
    with axis_register_configuration():
        results=dag.run(BuildConfig(root_dir=ROOT,vitis_version='2026.1'),force=True)
    assert all(x.success for x in results.values())
    dump(E/'layout.json',{'command_example':S.beats([S.hdr(1,0xf1234567,2,3)]),
                          'signed_input_example':S.beats([S.samples([-32768,-1,0,32767])]),
                          'response_example':S.beats(S.response([[32767]*16],[-32768]*16,0xffffffff))})


def check_stage(stage):
    report={}
    for name,sc in S.scenarios().items():
        d=E/'vectors'/name/stage
        got=S.beats(read_bursts(d))
        st=json.loads((d/'status.json').read_text())
        left=S.beats(read_bursts(d/'unread'))
        want=S.beats(sc.expected)
        status={k:st[k] for k in sc.status}
        verdict=S.compare_observation(sc,read_bursts(d),status,st['consumed'],read_bursts(d/'unread'))
        ok=verdict['pass'] and st['pass']
        report[name]={'pass':ok,'expected_status':sc.status,'observed_status':status,
                      'expected_consumed':sc.consumed,'observed_consumed':st['consumed'],
                      'expected_output':want,'observed_output':got,
                      'expected_unread':S.beats(sc.stimulus)[sc.consumed:],'observed_unread':left}
    dump(E/f'{stage}_checks.json',report)
    assert all(x['pass'] for x in report.values()),f'{stage}: some scenarios failed'


def vitis(stage):
    logpath=E/f'{stage}.log'
    if logpath.exists():
        archive=E/'history'/f'{stage}_{time.time_ns()}.log'
        archive.parent.mkdir(exist_ok=True)
        shutil.copy2(logpath,archive)
    try:
        result=toolchain.run_vitis_hls(ROOT/'run.tcl',work_dir=ROOT,capture_output=True,env={'MATVEC_STAGE':stage})
        log=result.stdout or ''
    except subprocess.CalledProcessError as exc:
        log=exc.stdout or str(exc)
        (E/f'{stage}.log').write_text(log)
        print(log[-12000:])
        raise
    (E/f'{stage}.log').write_text(log)
    print(log[-6000:])
    if stage in ('csim','cosim'): check_stage(stage)
    if stage=='synth':
        target=E/'synthesis'
        target.mkdir(exist_ok=True)
        for p in (ROOT/'hls_proj/solution1/syn/report').glob('*'):
            if p.is_file(): shutil.copy2(p,target/p.name)
        # Inspect actual synthesis binding, not merely the requested pragma.
        binding=[line for line in log.splitlines() if "Setting interface mode on port 'matvec/s_in_" in line]
        dump(E/'input_interface.json',{'binding_lines':binding,
            'no_registered_input':bool(binding) and all('register' not in line for line in binding),
            'source':'evidence/synth.log'})
        assert binding and all('register' not in line for line in binding), 'Input interface still registered'
        shutil.copytree(ROOT/'hls_proj/solution1/syn/verilog',E/'synthesized_rtl',dirs_exist_ok=True)
    if stage=='cosim':
        shutil.copytree(ROOT/'hls_proj/solution1/sim/report',E/'cosim_report',dirs_exist_ok=True)


def capture():
    from waveflow.scripts.xsim_vcd import run_xsim_vcd
    path=run_xsim_vcd(top='matvec',comp='hls_proj',out='matvec.vcd',trace_level='all',workdir=ROOT)
    dump(E/'capture.json',{'path':str(path.relative_to(ROOT))})


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--through',choices=['summary','py_sim'],help='summary executes every required stage; py_sim executes Python and generation')
    ap.add_argument('--stage',choices=['generate','csim','synth','cosim','capture','rtl','analyze','report','all'],default='all')
    a=ap.parse_args()
    if a.through: a.stage='all' if a.through=='summary' else 'generate'
    E.mkdir(exist_ok=True)
    stages=['generate','csim','synth','cosim','rtl','analyze','report'] if a.stage=='all' else [a.stage]
    failures=[]
    for stage in stages:
        start=time.time()
        # Archive observations before overwriting them on any rerun.
        archive=E/'history'/f'{stage}_{time.time_ns()}'
        files={'generate':['python_checks.json','independent.json','negative_controls.json','layout.json'],
               'csim':['csim_checks.json'],'cosim':['cosim_checks.json'],
               'analyze':['rtl_checks.json','synthesis_metrics.json','performance.json']}.get(stage,[])
        for file in files:
            if (E/file).exists():
                archive.mkdir(exist_ok=True)
                shutil.copy2(E/file,archive/file)
        history={'stage':stage,'started_unix':start,'prompt_version':3,
                 'prompt_sha256':hashlib.sha256((ROOT.parent/'prompt.md').read_bytes()).hexdigest(),
                 'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.iterdir()
                                  if p.suffix in ('.py','.tpp','.cpp','.tcl','.sv','.sh')}}
        try:
            if stage=='generate': generate()
            elif stage in ('csim','synth','cosim'): vitis(stage)
            elif stage=='capture': capture()
            elif stage=='rtl':
                from rtl_run import run
                run()
            elif stage=='analyze':
                from analyze import analyze
                analyze()
            elif stage=='report':
                from report import write_report
                write_report()
            history['pass']=True
        except Exception as exc:
            history.update({'pass':False,'error':str(exc)})
            failures.append(stage)
            if a.stage!='all' or stage not in ('rtl','analyze'):
                raise
            print(f'{stage} failed; continuing evidence/report generation: {exc}',flush=True)
        finally:
            history['elapsed_seconds']=time.time()-start
            with (E/'run_history.jsonl').open('a') as f: f.write(json.dumps(history)+'\n')
    if 'report' in stages and 'report' not in failures:
        # Include this report invocation's completed history record.
        from report import write_report
        write_report()
    if failures:
        raise SystemExit(1)

if __name__=='__main__': main()
