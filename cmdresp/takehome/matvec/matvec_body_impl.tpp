// Hand-written kernel body. Serializers and top-level interfaces are Waveflow generated.
#include "include/cmd_hdr.h"
#include "include/resp_hdr.h"
#include "include/int32_array_utils.h"
#include "include/int64_array_utils.h"
namespace matvec_impl {
static inline void fail(unsigned code, ap_uint<32> id,
                        ap_uint<1>& halted, ap_uint<8>& error, ap_uint<32>& tx_id) {
#pragma HLS INLINE
    halted=1; error=code; tx_id=id;
}
template<int in_bw,int out_bw>
void body(hls::stream<streamutils::axi4s_word<in_bw>>& s_in,
          hls::stream<streamutils::axi4s_word<out_bw>>& m_out,
          ap_uint<1>& halted, ap_uint<8>& error, ap_uint<32>& tx_id) {
#pragma HLS INLINE
    static_assert(in_bw==32 && out_bw==32,"32-bit wire contract");
    halted=0; error=0; tx_id=0;
    bool configured=false;
    unsigned rows=0, cols=0;
    ap_int<16> matrix[256], staging[256], vector[16];
    command_loop: while (true) {
        ap_uint<32> hw[4]={0,0,0,0};
        CmdHdr h;
        header_loop: for (int j=0;j<4;++j) {
            auto beat=s_in.read();
            hw[j]=beat.data;
            if (bool(beat.last)!=(j==3)) {
                h.template read_array<32>(hw);
                fail(1,h.tx_id,halted,error,tx_id);
                return;
            }
        }
        h.template read_array<32>(hw);
        const unsigned op=h.opcode;
        if (op>2) { fail(2,h.tx_id,halted,error,tx_id); return; }
        if (op==2 && !configured) { fail(3,h.tx_id,halted,error,tx_id); return; }
        if ((op==0 && (h.arg0!=0 || h.arg1!=0)) ||
            (op==1 && (h.arg0<1 || h.arg0>16 || h.arg1<1 || h.arg1>16)) ||
            (op==2 && (h.arg0!=cols || h.arg1!=0))) {
            fail(4,h.tx_id,halted,error,tx_id); return;
        }
        if (op==0) return;
        const unsigned count=op==1 ? unsigned(h.arg0*h.arg1) : cols;
        payload_loop: for (unsigned j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=256
            int32_array_utils::value_type lane[1];
            streamutils::tlast_status tl;
            int32_array_utils::read_axi4_stream_lane<32>(s_in,lane,1,tl);
            bool last=tl==streamutils::tlast_status::tlast_at_end;
            if (op==1) staging[j]=ap_int<16>(lane[0]);
            else vector[j]=ap_int<16>(lane[0]);
            if (last!=(j+1==count)) {
                fail(last?5:6,h.tx_id,halted,error,tx_id); return;
            }
        }
        if (op==1) {
            commit_loop: for (unsigned j=0;j<count;++j) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=256
                matrix[j]=staging[j];
            }
            rows=h.arg0; cols=h.arg1; configured=true;
        } else {
            RespHdr resp;
            resp.opcode=2; resp.tx_id=h.tx_id; resp.rows=rows;
            resp.template write_axi4_stream<32>(m_out,true);
            row_loop: for (unsigned r=0;r<rows;++r) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
                ap_int<64> acc=0;
                dot_loop: for (unsigned c=0;c<cols;++c) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=1 max=16
                    ap_int<32> product=matrix[r*cols+c]*vector[c];
                    acc+=ap_int<64>(product);
                }
                int64_array_utils::value_type result[1]={acc};
                // The generated wide scalar AXIS writer ignores TLAST in this
                // Waveflow version. Use its array serializer, then frame the words.
                ap_uint<32> packed[int64_array_utils::get_nwords<32>(1)];
                int64_array_utils::write_array_lane<32>(result,packed,1);
                result_words: for (int w=0;w<2;++w) {
                    streamutils::write_axi4_word<32>(m_out,packed[w],r+1==rows && w==1);
                }
            }
        }
    }
}
}
