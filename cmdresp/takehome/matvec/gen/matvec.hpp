#pragma once

#include <ap_int.h>
#include <ap_fixed.h>

#include "include/streamutils_hls.h"

void matvec(
    hls::stream<streamutils::axi4s_word<32>>& s_in,
    hls::stream<streamutils::axi4s_word<32>>& m_out,
    ap_uint<1>& halted,
    ap_uint<8>& error,
    ap_uint<32>& tx_id
);

namespace matvec_impl {
    template <int in_bw, int out_bw>
    void body(hls::stream<streamutils::axi4s_word<in_bw>>& s_in, hls::stream<streamutils::axi4s_word<out_bw>>& m_out, ap_uint<1>& halted, ap_uint<8>& error, ap_uint<32>& tx_id);
}

#include "../matvec_body_impl.tpp"
