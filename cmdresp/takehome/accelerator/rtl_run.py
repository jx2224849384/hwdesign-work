"""Run the complete suite against unmodified synthesized RTL, with full input queues."""
from pathlib import Path
import json, subprocess, shutil, time, os
import scenarios as S
ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'

def run():
    # Preserve earlier pin observations before any rerun, including failed runs.
    if (E/'rtl').exists():
        shutil.copytree(E/'rtl', E/'history'/f'rtl_{time.time_ns()}')
    if (E/'rtl_sim.log').exists():
        shutil.copy2(E/'rtl_sim.log', E/'history'/f'rtl_{time.time_ns()}.log')
    for name,sc in S.scenarios().items():
        d=E/'vectors'/name
        (E/'rtl'/name).mkdir(parents=True,exist_ok=True)
        for f,bs in [('input.txt',sc.stimulus),('output.txt',sc.expected)]:
            (d/f).write_text(''.join(f'{w:08x} {last}\n' for w,last in S.beats(bs)))
    work=ROOT/'rtl_work'
    work.mkdir(exist_ok=True)
    bindir=Path(os.environ.get('MATVEC_VIVADO_BIN','/eda/xilinx/2026.1/Vivado/bin'))
    rtl=sorted((ROOT/'hls_proj/solution1/syn/verilog').glob('*.v'))
    tcl=ROOT/'rtl_trace.tcl'
    tcl.write_text('open_vcd '+str(E/'rtl.vcd')+'\nlog_vcd /rtl_tb/dut/*\nrun all\nclose_vcd\nquit\n')
    commands=[ [str(bindir/'xvlog'),'--sv',str(ROOT/'rtl_tb.sv'),*[str(p) for p in rtl]],
               [str(bindir/'xelab'),'rtl_tb','-s','matvec_rtl','-debug','typical'],
               [str(bindir/'xsim'),'matvec_rtl','-tclbatch',str(tcl),'-testplusarg','ROOT='+str(E)] ]
    logs=[]
    for cmd in commands:
        result=subprocess.run(cmd,cwd=work,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        logs.append(result.stdout)
        log=E/'rtl_sim.log'
        log.write_text('\n'.join(logs))
        if result.returncode:
            print(result.stdout[-10000:])
            raise RuntimeError(f'{cmd[0]} exited {result.returncode}')
    print(logs[-1][-6000:])
    statuses={n:json.loads((E/'rtl'/n/'status.json').read_text()) for n in S.scenarios()}
    # Xsim can exit 0 after $fatal, so enforce the observed outcomes in Python too.
    if not all(v['pass'] for v in statuses.values()) or f'PIN_RTL_SUMMARY tests={len(statuses)} failures=0' not in logs[-1]:
        raise RuntimeError('Pin-level RTL scenarios failed; see evidence/rtl/*/status.json')
if __name__=='__main__': run()
