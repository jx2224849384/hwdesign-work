"""Independent intent fixtures, serialization, and strict recording comparisons."""
from dataclasses import dataclass, field
import numpy as np
from waveflow.hw.arrayutils import write_array
from waveflow.utils.burst_io import StreamBurst
from matvec import CmdHdr, RespHdr, I32, I64, matvec_eval

def hdr(op, tx=0, a0=0, a1=0):
    h = CmdHdr()
    h.opcode, h.tx_id, h.arg0, h.arg1 = op, tx, a0, a1
    return StreamBurst(h.serialize(word_bw=32))

def samples(xs, last=True):
    return StreamBurst(write_array(np.asarray(xs, np.int32).reshape(-1), elem_type=I32, word_bw=32), last)

def config(a, tx=10):
    a = np.asarray(a, np.int16)
    return [hdr(1, tx, *a.shape), samples(a)]

def data(x, tx=20):
    return [hdr(2, tx, len(x), 0), samples(x)]

def response(a, x, tx=20):
    # Oracle uses NumPy int64 @, not the scalar golden implementation.
    ys = np.asarray(a, np.int64) @ np.asarray(x, np.int64)
    h = RespHdr()
    h.opcode, h.tx_id, h.rows = 2, tx, len(ys)
    return [StreamBurst(h.serialize(word_bw=32)),
            StreamBurst(write_array(ys, elem_type=I64, word_bw=32))]

def beats(bursts):
    return [(int(w), int(b.tlast and j+1 == len(b.words)))
            for b in bursts for j, w in enumerate(b.words)]

def from_beats(words):
    out, cur = [], []
    for w, last in words:
        cur.append(w)
        if last:
            out.append(StreamBurst(np.asarray(cur, np.uint32), True))
            cur = []
    if cur:
        out.append(StreamBurst(np.asarray(cur, np.uint32), False))
    return out

@dataclass
class Scenario:
    stimulus: list
    expected: list
    status: dict
    consumed: int
    purpose: str
    recovery: str | None = None
    # DATA tx_id -> first vector beat offset, for measured RTL latency.
    vectors: dict = field(default_factory=dict)


def scenarios():
    tests = {}
    clear = {"halted": 0, "error": 0, "tx_id": 0}
    sentinel = [hdr(0xdeadbeef, 0xabcdef01, 0x12345678, 0xfedcba98)]
    base = np.asarray([[1,2],[3,4]], np.int16)
    def good(name, stim, out, purpose, vectors=None):
        prefix = stim + [hdr(0, 0xffffffff)]
        tests[name] = Scenario(prefix + sentinel, out, clear.copy(), len(beats(prefix)), purpose,
                               vectors=vectors or {})
    def bad(name, prefix, out, error, tx, purpose, tail=None):
        recovery = "recover_" + name
        tests[name] = Scenario(prefix + (tail or []) + sentinel, out,
            {"halted":1, "error":error, "tx_id":tx}, len(beats(prefix)), purpose, recovery)
        good(recovery, config([[7,-3,2]]) + data([2,4,-1], 0xffffffff),
             response([[7,-3,2]], [2,4,-1], 0xffffffff), "Fresh CONFIG/DATA/END after " + name)
    good("end_unconfigured", [], [], "END without CONFIG; sentinel unread")
    good("config_only", config(base), [], "CONFIG produces no response")
    good("example_17_39", config(base) + data([5,6]), response(base, [5,6]), "Hand example [17,39]")
    a = [[1,-2,3],[-1,0,2]]
    good("example_negative", config(a) + data([2,1,-1]), response(a, [2,1,-1]), "Hand example [-3,-4]")
    for name, a, x in [
        ("one_by_one", [[-32768]], [-32768]),
        ("one_by_sixteen", [[32767]*16], [-32768]*16),
        ("sixteen_by_one", [[-32768],[32767]]*8, [-32768]),
        ("zeros", np.zeros((7,5), np.int16), [0]*5),
        ("positive_overflow32", np.full((16,16), -32768, np.int16), [-32768]*16),
        ("negative_overflow32", np.full((16,16), 32767, np.int16), [-32768]*16),
        ("signed_extremes", [[-32768,32767,-1,0,1],[32767,-32768,0,1,-1]], [-32768,32767,1,-1,0])]:
        good(name, config(a) + data(x), response(a, x), name.replace('_',' '))
    a2 = [[-2,5,7]]
    good("reconfigure_dimensions", config(base) + data([1,2],30) + config(a2) + data([2,0,-3],31)
         + config([[4]]) + config(base) + data([-1,3],32),
         response(base,[1,2],30)+response(a2,[2,0,-3],31)+response(base,[-1,3],32),
         "Replace matrices and dimensions; back-to-back CONFIG")
    good("clear_accumulators", config(base)+data([5,6],33)+data([0,0],34)+data([5,6],35),
         response(base,[5,6],33)+response(base,[0,0],34)+response(base,[5,6],35), "Per-vector accumulation resets")
    good("repeated_tx_id", config(base)+data([5,6],0xffffffff)+data([-1,2],0xffffffff),
         response(base,[5,6],0xffffffff)+response(base,[-1,2],0xffffffff), "Repeated full-width transaction ID echoed unchanged")
    good("source_gaps", config(base)+data([5,6]), response(base,[5,6]), "Pin producer pauses in header and payload; temporary emptiness stalls")
    good("output_backpressure", config(base)+data([5,6]), response(base,[5,6]), "Pin sink pauses; output remains stable and correctly framed")
    bad("activation_unconfigured", [hdr(2,0xffffffff,2,0)], [], 3,0xffffffff,
        "Successful previous activation must not leave configuration available", [samples([5,6])])
    rng = np.random.default_rng(20261104)
    stim, exp = [], []
    for j,(r,c) in enumerate([(3,7),(7,3),(15,16),(16,15),(8,9),(2,2)]):
        a = rng.integers(-32768,32768,(r,c),dtype=np.int16)
        stim += config(a,100+j)
        for k in range(2):
            x = rng.integers(-32768,32768,c,dtype=np.int16)
            stim += data(x,200+j*2+k)
            exp += response(a,x,200+j*2+k)
    good("random_rectangular", stim, exp, "Deterministic int16 matrices, NumPy int64 oracle")
    # Eight vectors in one activation: documented throughput measurement sequence.
    a = rng.integers(-100,101,(16,16),dtype=np.int16)
    stim, exp, vectors = config(a), [], {}
    for j in range(8):
        x = rng.integers(-32768,32768,16,dtype=np.int16)
        vectors[str(1000+j)] = len(beats(stim))+4
        stim += data(x,1000+j)
        exp += response(a,x,1000+j)
    good("performance_16x16", stim, exp, "Eight consecutive 16x16 vectors, continuous source and ready sink", vectors)

    for op,label in [(0,"end"),(1,"config"),(2,"data"),(99,"unknown")]:
        full = hdr(op, 0xf0000100+op, 0, 99).words
        for n in (1,2,3):
            bad(f"header_early_{label}_{n}", [StreamBurst(full[:n])], [], 1,
                0 if n==1 else 0xf0000100+op, "Framing precedes opcode/configuration/argument errors",
                [StreamBurst(full[n:])])
        bad(f"header_missing_{label}", [StreamBurst(full,False)], [], 1, 0xf0000100+op,
            "Missing header TLAST detected on fourth beat, no read-ahead")
    bad("unknown_opcode", [hdr(0xffffffff,301,0,99)], [], 2,301,"Opcode before arguments", [samples([8,9])])
    bad("data_unconfigured", [hdr(2,302,0,99)], [], 3,302,"Configuration availability before invalid args", [samples([8])])
    for r,c in [(0,1),(1,0),(17,1),(1,17),(0xffffffff,16)]:
        bad(f"invalid_dimensions_{r}_{c}", [hdr(1,303,r,c)], [], 4,303,"Validate dimensions before payload", [samples([1,2])])
    for n,reserved,label in [(0,0,"zero_length"),(1,0,"wrong_length"),(2,1,"reserved")]:
        bad("data_"+label, config(base)+[hdr(2,304,n,reserved)], [], 4,304,
            "Configured DATA arguments before malformed payload", [samples([1])])
    for arg0,arg1 in [(1,0),(0,1)]:
        bad(f"end_reserved_{arg0}_{arg1}",[hdr(0,305,arg0,arg1)],[],4,305,"END reserved argument validation")
    for sent in (1,3):
        bad(f"config_early_{sent}",[hdr(1,306,2,2),samples([1,2,3][:sent])],[],5,306,"No response or partial CONFIG commit")
    bad("config_missing",[hdr(1,307,2,2),samples([1,2,3,4],False)],[],6,307,"No read beyond expected matrix end",[samples([99])])
    bad("data_early",config(base)+[hdr(2,308,2,0),samples([1])],[],5,308,"Failed DATA emits no header or results")
    bad("data_missing",config(base)+[hdr(2,309,2,0),samples([1,2],False)],[],6,309,"Failed DATA emits nothing; excess words unread",[samples([99])])
    bad("failed_reconfiguration",config(base)+data([5,6],310)+[hdr(1,311,1,3),samples([9])],
        response(base,[5,6],310),5,311,"Prior output retained; partial replacement not committed")
    bad("failed_data_after_success",config(base)+data([5,6],312)+[hdr(2,313,2),samples([1])],
        response(base,[5,6],312),5,313,"Prior successful response preserved exactly")
    # Boundary stress: detect every possible early position of a maximum vector.
    for count in range(1,16):
        bad(f"data_early16_{count}",config([[1]*16])+[hdr(2,400+count,16),samples([1]*count)],
            [],5,400+count,"Early TLAST at each maximum-vector position")
    bad("config_early256_255",[hdr(1,500,16,16),samples([1]*255)],[],5,500,
        "Maximum matrix incomplete at penultimate word")
    bad("config_missing256",[hdr(1,501,16,16),samples([1]*256,False)],[],6,501,
        "Maximum matrix missing TLAST; next sentinel must remain unread")
    bad("data_missing16",config([[1]*16])+[hdr(2,502,16),samples([1]*16,False)],[],6,502,
        "Maximum vector missing TLAST; next sentinel must remain unread")
    return tests


def independent_checks():
    checks = {}
    for name,a,x,y in [("hand_17_39",[[1,2],[3,4]],[5,6],[17,39]),
                        ("hand_negative",[[1,-2,3],[-1,0,2]],[2,1,-1],[-3,-4])]:
        got = matvec_eval(a,x).tolist()
        checks[name] = {"expected":y,"observed":got,"pass":got==y}
    rng = np.random.default_rng(991)
    for r in range(1,17):
        for c in range(1,17):
            a = rng.integers(-32768,32768,(r,c),dtype=np.int16)
            x = rng.integers(-32768,32768,c,dtype=np.int16)
            expected = (a.astype(np.int64) @ x.astype(np.int64)).tolist()
            got = matvec_eval(a,x).tolist()
            checks[f"numpy_{r}x{c}"]={"expected":expected,"observed":got,"pass":got==expected}
    assert all(c["pass"] for c in checks.values())
    return checks


def compare_observation(sc, output, status, consumed, unread):
    """Shared strict checker, also tested against deliberately corrupted observations."""
    checks = {
        'response_words_and_tlast': beats(output)==beats(sc.expected),
        'status': status==sc.status,
        'accepted_count': consumed==sc.consumed,
        'unread_words_and_tlast': beats(unread)==beats(sc.stimulus)[sc.consumed:],
    }
    return {'pass':all(checks.values()), 'checks':checks}


def negative_controls():
    sc=scenarios()['example_17_39']
    left=from_beats(beats(sc.stimulus)[sc.consumed:])
    good=beats(sc.expected)
    wrong_value=good.copy(); wrong_value[3]=(good[3][0]^1,good[3][1])
    wrong_tlast=good.copy(); wrong_tlast[-1]=(good[-1][0],0)
    corruptions={
        'wrong_result_bit':(from_beats(wrong_value), sc.status, sc.consumed, left),
        'missing_output_tlast':(from_beats(wrong_tlast), sc.status, sc.consumed, left),
        'extra_input_accepted':(sc.expected, sc.status, sc.consumed+1,
                                from_beats(beats(sc.stimulus)[sc.consumed+1:])),
        'uncleared_status':(sc.expected, {'halted':1,'error':6,'tx_id':20}, sc.consumed,left),
    }
    result={name:compare_observation(sc,*args) for name,args in corruptions.items()}
    assert all(not r['pass'] for r in result.values()), 'Checker accepted corrupted observation'
    return result
