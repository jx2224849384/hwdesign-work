"""Beat-accurate functional model, with no cycle/timing model."""
import numpy as np
from waveflow.hw.arrayutils import read_array, write_array
from waveflow.utils.burst_io import StreamBurst
from matvec import CmdHdr, RespHdr, I32, I64, matvec_eval

def matvec_stream_model(bursts):
    words=[(int(w),bool(b.tlast and i+1==len(b.words))) for b in bursts for i,w in enumerate(b.words)]
    pos=0
    out=[]
    matrix=None
    status={"halted":0,"error":0,"tx_id":0}
    def finish(error=0,tx=0):
        return {"out":out,"status": {"halted":int(error!=0),"error":error,"tx_id":tx},"consumed":pos}
    def read():
        nonlocal pos
        if pos==len(words):
            raise ValueError("Input incomplete: hardware waits for another beat, not a protocol error")
        w=words[pos]
        pos+=1
        return w
    while True:
        hw=[0]*4
        for i in range(4):
            hw[i],last=read()
            if last != (i==3):
                h=CmdHdr().deserialize(hw,word_bw=32)
                return finish(1,int(h.tx_id))
        h=CmdHdr().deserialize(hw,word_bw=32)
        op,tx,a0,a1=map(int,(h.opcode,h.tx_id,h.arg0,h.arg1))
        if op not in (0,1,2): return finish(2,tx)
        if op==2 and matrix is None: return finish(3,tx)
        if (op==0 and (a0 or a1)) or (op==1 and not(1<=a0<=16 and 1<=a1<=16)) or (op==2 and (a0!=matrix.shape[1] or a1)):
            return finish(4,tx)
        if op==0: return finish()
        n=a0*a1 if op==1 else a0
        payload=[]
        for i in range(n):
            w,last=read()
            payload.append(w)
            if last != (i==n-1): return finish(5 if last else 6,tx)
        values=read_array(payload,elem_type=I32,word_bw=32,shape=n).val
        if op==1:
            matrix=values.astype(np.int16).reshape(a0,a1)
        else:
            y=matvec_eval(matrix,values.astype(np.int16))
            r=RespHdr()
            r.opcode,r.tx_id,r.rows=2,tx,len(y)
            out += [StreamBurst(r.serialize(word_bw=32)),StreamBurst(write_array(y,elem_type=I64,word_bw=32))]
