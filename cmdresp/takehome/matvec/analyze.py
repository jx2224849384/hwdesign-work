"""Analyze observed RTL handshakes/status and synthesis XML, never substitute expected data."""
from pathlib import Path
import csv, json, xml.etree.ElementTree as ET
from waveflow.hw.arrayutils import read_array
from matvec import RespHdr, I64
import scenarios as S
ROOT=Path(__file__).resolve().parent
E=ROOT/'evidence'

def dump(p,data): p.write_text(json.dumps(data,indent=2)+'\n')

def load_beats(path,clocked=False):
    records=[]
    for line in path.read_text().splitlines():
        a=line.split()
        if clocked: records.append({'cycle':int(a[0]),'data':int(a[1],16),'last':int(a[2])})
        else: records.append([int(a[0],16),int(a[1])])
    return records

def analyze():
    synth=ET.parse(E/'synthesis/matvec_csynth.xml').getroot()
    base='PerformanceEstimates/SummaryOfTimingAnalysis/EstimatedClockPeriod'
    period=float(synth.findtext(base))
    resources={c.tag:int(c.text) for c in synth.find('AreaEstimates/Resources')}
    loops=[]
    for p in sorted((E/'synthesis').glob('*_csynth.xml')):
        tree=ET.parse(p).getroot()
        for loop in tree.findall('.//SummaryOfLoopLatency/*'):
            ii=loop.findtext('PipelineII')
            if ii:
                loops.append({'loop':loop.tag,'II':int(ii),'source':str(p.relative_to(ROOT)),
                    'xpath':f'PerformanceEstimates/SummaryOfLoopLatency/{loop.tag}/PipelineII'})
    synthesis={'estimated_clock_ns':period,'clock_target_ns':10,'clock_pass':period<10,
               'requested_clock_ns':float(synth.findtext('UserAssignments/TargetClockPeriod')),
               'clock_uncertainty_ns':float(synth.findtext('UserAssignments/ClockUncertainty')),
               'resources':resources,'loops':loops,'source':'evidence/synthesis/matvec_csynth.xml',
               'clock_xpath':base,'resources_xpath':'AreaEstimates/Resources'}
    dump(E/'synthesis_metrics.json',synthesis)
    report={}
    perf=None
    for name,sc in S.scenarios().items():
        d=E/'rtl'/name
        status=json.loads((d/'status.json').read_text())
        ins=load_beats(d/'input_handshakes.txt',True)
        outs=load_beats(d/'output_handshakes.txt',True)
        unread=load_beats(d/'unread.txt')
        input_pairs=[[b['data'],b['last']] for b in ins]
        output_pairs=[[b['data'],b['last']] for b in outs]
        expected_in=[list(x) for x in S.beats(sc.stimulus)[:sc.consumed]]
        expected_out=[list(x) for x in S.beats(sc.expected)]
        expected_left=[list(x) for x in S.beats(sc.stimulus)[sc.consumed:]]
        observed_st={k:status[k] for k in sc.status}
        cycles=list(csv.DictReader((d/'cycles.csv').open()))
        cnums=[int(x['cycle']) for x in cycles]
        assert all(b==a+1 for a,b in zip(cnums,cnums[1:])),name+': non-contiguous cycle labels'
        sentinel_cycles=[int(x['cycle']) for x in cycles if int(x['cycle'])>status['done_cycle']
                         and int(x['in_valid'])==1 and int(x['in_ready'])==0
                         and int(x['in_data'],16)==expected_left[0][0]
                         and int(x['in_last'])==expected_left[0][1]] if expected_left else []
        checks={'input_prefix':input_pairs==expected_in,'response_bits_tlast':output_pairs==expected_out,
                'status':observed_st==sc.status,'consumed_count':status['consumed']==sc.consumed,
                'unread_suffix':unread==expected_left,'sentinel_present_and_stalled':len(sentinel_cycles)>=20,
                'testbench_pass':status['pass']}
        report[name]={'pass':all(checks.values()),'checks':checks,'expected_status':sc.status,
                      'observed_status':observed_st,'expected_consumed':sc.consumed,
                      'observed_consumed':status['consumed'],'expected_output':expected_out,'observed_output':output_pairs,
                      'expected_unread':expected_left,'observed_unread':unread,'recovery':sc.recovery,
                      'sentinel_stalled_cycles':sentinel_cycles,
                      'sources':{f:str((d/f).relative_to(ROOT)) for f in
                          ('input_handshakes.txt','output_handshakes.txt','status.json','unread.txt','cycles.csv')}}
        if name=='performance_16x16':
            results=[]
            pos=0
            while pos<len(outs):
                header=RespHdr().deserialize([x['data'] for x in outs[pos:pos+3]],word_bw=32)
                rows=int(header.rows)
                end=pos+3+2*rows-1
                tx=str(int(header.tx_id))
                first_in=ins[sc.vectors[tx]]['cycle']
                last_in=ins[sc.vectors[tx]+15]['cycle']
                last_out=outs[end]['cycle']
                window=[x for x in cycles if first_in<=int(x['cycle'])<=last_in]
                output_window=[x for x in cycles if first_in<=int(x['cycle'])<=last_out]
                continuous=all(int(x['in_valid'])==1 for x in window)
                no_backpressure=all(int(x['out_ready'])==1 for x in output_window)
                results.append({'tx_id':int(tx),'first_vector_handshake_cycle':first_in,
                                'last_vector_handshake_cycle':last_in,'final_result_handshake_cycle':last_out,
                                'latency_cycles':last_out-first_in,'continuous_input':continuous,
                                'no_output_backpressure':no_backpressure,'latency_pass':last_out-first_in<=10000,
                                'input_event_index':sc.vectors[tx],'output_event_index':end})
                pos=end+1
            assert len(results)==8
            interval=results[-1]['final_result_handshake_cycle']-results[0]['final_result_handshake_cycle']
            full=results[-1]['final_result_handshake_cycle']-results[0]['first_vector_handshake_cycle']
            perf={'sequence':'performance_16x16, DATA tx_id 1000..1007 under one CONFIG',
                  'vectors':results,'maximum_latency_cycles':max(v['latency_cycles'] for v in results),
                  'latency_target_cycles':10000,
                  'latency_pass':all(v['latency_pass'] and v['continuous_input'] and v['no_output_backpressure'] for v in results),
                  'completion_intervals':7,'completion_interval_cycles':interval,
                  'vectors_per_cycle':7/interval,'full_window_cycles':full,'full_window_vectors_per_cycle':8/full,
                  'source_input':str((d/'input_handshakes.txt').relative_to(ROOT)),
                  'source_output':str((d/'output_handshakes.txt').relative_to(ROOT)),
                  'source_flow_control':str((d/'cycles.csv').relative_to(ROOT))}
    dump(E/'rtl_checks.json',report)
    dump(E/'performance.json',perf)
    assert all(r['pass'] for r in report.values()), 'RTL full-queue comparisons failed'
    # Performance misses are reported honestly; they do not trigger redesign or hide functional results.
    print('RTL verified scenarios:',len(report),'estimated clock:',period,'latency:',perf['maximum_latency_cycles'])
if __name__=='__main__': analyze()
