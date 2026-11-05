#include "gen/matvec.hpp"
#include "include/bundle_tb.h"
#include <fstream>
#include <string>
#include <vector>
#include <cstdio>
using Beat=streamutils::axi4s_word<32>;
static std::vector<Beat> drain(hls::stream<Beat>& s) {
    std::vector<Beat> v;
    while(!s.empty()) v.push_back(s.read());
    return v;
}
static bool same(const std::vector<Beat>& a,const std::vector<Beat>& b) {
    if(a.size()!=b.size()) return false;
    for(unsigned i=0;i<a.size();++i)
        if(a[i].data!=b[i].data || a[i].last!=b[i].last || a[i].keep!=15 || a[i].strb!=15) return false;
    return true;
}
static void record(const std::vector<Beat>& a,const std::string& path) {
    hls::stream<Beat> s;
    for(const auto& w:a) s.write(w);
    wf::record_stream<32>(s,path);
}
int main(int argc,char** argv) {
    if(argc!=3) return 2;
    std::string root=argv[1], stage=argv[2], name;
    std::ifstream list(root+"/scenarios.txt");
    if(!list) return 3;
    ap_uint<32> halted=1;
    ap_uint<32> error=255;
    ap_uint<32> tx_id=0xffffffff;
    int failed=0, run=0;
    while(list>>name) {
        std::string d=root+"/"+name;
        hls::stream<Beat> in,out,expected,unread;
        wf::play_stream<32>(d+"/in",in);
        wf::play_stream<32>(d+"/expected",expected);
        wf::play_stream<32>(d+"/expected/unread",unread);
        const unsigned before=in.size();
        matvec(in,out,halted,error,tx_id);
        unsigned consumed=before-in.size();
        auto got=drain(out), left=drain(in), want=drain(expected), want_left=drain(unread);
        unsigned eh,ee,et,ec;
        std::ifstream meta(d+"/expected.txt");
        meta>>eh>>ee>>et>>ec;
        bool ok=meta.good() && same(got,want) && same(left,want_left) &&
            unsigned(halted)==eh && unsigned(error)==ee && unsigned(tx_id)==et && consumed==ec;
        record(got,d+"/"+stage);
        record(left,d+"/"+stage+"/unread");
        std::ofstream st(d+"/"+stage+"/status.json");
        st<<"{\"halted\":"<<unsigned(halted)<<",\"error\":"<<unsigned(error)
          <<",\"tx_id\":"<<unsigned(tx_id)<<",\"consumed\":"<<consumed<<",\"pass\":"<<(ok?"true":"false")<<"}\n";
        std::printf("%s %s halted=%u error=%u tx_id=%u consumed=%u unread=%zu\n",name.c_str(),
            ok?"PASS":"FAIL",unsigned(halted),unsigned(error),unsigned(tx_id),consumed,left.size());
        ++run;
        if(!ok) ++failed;
    }
    return failed || !run ? 1:0;
}
