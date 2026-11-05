#ifndef INCLUDE_RESP_HDR_TB_H
#define INCLUDE_RESP_HDR_TB_H

#include <cctype>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include "streamutils_tb.h"

#define WAVEFLOW_ENABLE_RESP_HDR_TB_H_MEMBERS
#include "resp_hdr.h"
#undef WAVEFLOW_ENABLE_RESP_HDR_TB_H_MEMBERS

inline void RespHdr::dump_json(std::ostream& os, int indent, int level) const {
    const int step = (indent < 0) ? 0 : indent;
    os << "{";
    os << "\n";
    for (int i = 0; i < (level + 1) * step; ++i) { os << ' '; }
    os << "\"opcode\": ";
    os << static_cast<unsigned long long>(this->opcode);
    os << ",";
    os << "\n";
    for (int i = 0; i < (level + 1) * step; ++i) { os << ' '; }
    os << "\"tx_id\": ";
    os << static_cast<unsigned long long>(this->tx_id);
    os << ",";
    os << "\n";
    for (int i = 0; i < (level + 1) * step; ++i) { os << ' '; }
    os << "\"rows\": ";
    os << static_cast<unsigned long long>(this->rows);
    os << "\n";
    for (int i = 0; i < (level) * step; ++i) { os << ' '; }
    os << "}";
}

inline void RespHdr::load_json(const std::string& json_text, size_t& pos) {
    streamutils::json_expect_char(json_text, pos, '{');
    bool seen_root_opcode = false;
    bool seen_root_tx_id = false;
    bool seen_root_rows = false;
    bool first = true;
    while (true) {
    streamutils::json_skip_ws(json_text, pos);
    if (pos < json_text.size() && json_text[pos] == '}') {
        ++pos;
        break;
    }
    if (!first) {
        streamutils::json_expect_char(json_text, pos, ',');
    }
    first = false;
    std::string key = streamutils::json_parse_string(json_text, pos);
    streamutils::json_expect_char(json_text, pos, ':');
    if (key == "opcode") {
        seen_root_opcode = true;
        this->opcode = static_cast<ap_uint<32>>(static_cast<unsigned long long>(streamutils::json_parse_number(json_text, pos)));
    }
    else if (key == "tx_id") {
        seen_root_tx_id = true;
        this->tx_id = static_cast<ap_uint<32>>(static_cast<unsigned long long>(streamutils::json_parse_number(json_text, pos)));
    }
    else if (key == "rows") {
        seen_root_rows = true;
        this->rows = static_cast<ap_uint<32>>(static_cast<unsigned long long>(streamutils::json_parse_number(json_text, pos)));
    }
    else {
        throw std::runtime_error("Malformed JSON: unexpected key for schema.");
    }
    }
    if (!seen_root_opcode) {
    throw std::runtime_error("Malformed JSON: missing required key 'opcode'.");
    }
    if (!seen_root_tx_id) {
    throw std::runtime_error("Malformed JSON: missing required key 'tx_id'.");
    }
    if (!seen_root_rows) {
    throw std::runtime_error("Malformed JSON: missing required key 'rows'.");
    }
}

inline void RespHdr::load_json(std::istream& is) {
    std::string json_text((std::istreambuf_iterator<char>(is)), std::istreambuf_iterator<char>());
    size_t pos = 0;
    streamutils::json_skip_ws(json_text, pos);
    this->load_json(json_text, pos);
    streamutils::json_skip_ws(json_text, pos);
    if (pos != json_text.size()) {
        throw std::runtime_error("Trailing characters after JSON object.");
    }
}

inline void RespHdr::dump_json_file(const char* file_path, int indent) const {
    std::ofstream ofs(file_path);
    if (!ofs) {
        throw std::runtime_error("Failed to open output JSON file.");
    }
    this->dump_json(ofs, indent);
}

inline void RespHdr::load_json_file(const char* file_path) {
    std::ifstream ifs(file_path);
    if (!ifs) {
        throw std::runtime_error("Failed to open input JSON file.");
    }
    this->load_json(ifs);
}

#endif // INCLUDE_RESP_HDR_TB_H