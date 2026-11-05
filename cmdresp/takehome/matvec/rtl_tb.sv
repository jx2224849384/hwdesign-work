`timescale 1ns/1ps
// Full-queue pin-level co-simulation. This testbench is hand-written, DUT RTL is not.
module rtl_tb;
reg ap_clk=0;
always #5 ap_clk=~ap_clk;
reg ap_rst_n=0;
reg [31:0] s_in_TDATA=0;
reg s_in_TVALID=0, s_in_TLAST=0;
wire s_in_TREADY;
wire [31:0] m_out_TDATA;
wire m_out_TVALID, m_out_TLAST;
wire [3:0] m_out_TKEEP,m_out_TSTRB;
reg m_out_TREADY=1;
reg [5:0] awaddr=0,araddr=0;
reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
reg [31:0] wdata=0;
wire awready,wready,bvalid,arready,rvalid;
wire [31:0] rdata;
wire [1:0] bresp,rresp;
wire interrupt;
matvec dut(.ap_clk(ap_clk),.ap_rst_n(ap_rst_n),
.s_in_TDATA(s_in_TDATA),.s_in_TVALID(s_in_TVALID),.s_in_TREADY(s_in_TREADY),
.s_in_TKEEP(4'hf),.s_in_TSTRB(4'hf),.s_in_TLAST(s_in_TLAST),
.m_out_TDATA(m_out_TDATA),.m_out_TVALID(m_out_TVALID),.m_out_TREADY(m_out_TREADY),
.m_out_TKEEP(m_out_TKEEP),.m_out_TSTRB(m_out_TSTRB),.m_out_TLAST(m_out_TLAST),
.s_axi_control_AWADDR(awaddr),.s_axi_control_AWVALID(awvalid),.s_axi_control_AWREADY(awready),
.s_axi_control_WDATA(wdata),.s_axi_control_WSTRB(4'hf),.s_axi_control_WVALID(wvalid),.s_axi_control_WREADY(wready),
.s_axi_control_BRESP(bresp),.s_axi_control_BVALID(bvalid),.s_axi_control_BREADY(bready),
.s_axi_control_ARADDR(araddr),.s_axi_control_ARVALID(arvalid),.s_axi_control_ARREADY(arready),
.s_axi_control_RDATA(rdata),.s_axi_control_RRESP(rresp),.s_axi_control_RVALID(rvalid),.s_axi_control_RREADY(rready),
.interrupt(interrupt));
integer cycle=0;
integer in_count=0,out_count=0,nin=0,nout=0;
integer fin,fout,ftrace,fstatus,fleft,flist,fmeta,rc,k,j,failed=0,test_failed=0,tests=0;
integer expected_h,expected_e,expected_c;
reg [31:0] expected_tx,observed_h,observed_e,observed_tx,ctrl;
reg [31:0] input_words[0:4095],output_words[0:4095];
integer input_last[0:4095],output_last[0:4095];
string root,name,dir;
reg active=0;
integer gap_left=0;
reg gap_used=0;
integer start_cycle,done_cycle,timeout_cycle;

// A producer holds each beat until accepted. The performance case has no source gaps.
always @(negedge ap_clk) begin
    if(active && in_count<nin) begin
        if(name=="example_negative" && in_count==12 && !gap_used) begin
            gap_left=4;
            gap_used=1;
        end
        if(gap_left>0) begin
            s_in_TVALID=0;
            gap_left=gap_left-1;
        end else begin
            s_in_TVALID=1;
            s_in_TDATA=input_words[in_count];
            s_in_TLAST=input_last[in_count];
        end
    end else s_in_TVALID=0;
end
always @(posedge ap_clk) begin
    cycle=cycle+1;
    if(active) begin
        $fwrite(ftrace,"%0d,%0d,%0d,%08x,%0d,%0d,%0d,%08x,%0d,%0d\n",cycle,
           s_in_TVALID,s_in_TREADY,s_in_TDATA,s_in_TLAST,
           m_out_TVALID,m_out_TREADY,m_out_TDATA,m_out_TLAST,dut.ap_done);
        if(s_in_TVALID && s_in_TREADY) begin
            $fwrite(fin,"%0d %08x %0d\n",cycle,s_in_TDATA,s_in_TLAST);
            in_count=in_count+1;
        end
        if(m_out_TVALID && m_out_TREADY) begin
            $fwrite(fout,"%0d %08x %0d\n",cycle,m_out_TDATA,m_out_TLAST);
            if(out_count>=nout || m_out_TDATA!==output_words[out_count] || m_out_TLAST!==output_last[out_count][0]) begin
                $display("OUTPUT_MISMATCH %s index=%0d got=%08x last=%0d",name,out_count,m_out_TDATA,m_out_TLAST);
                test_failed=1;
            end
            out_count=out_count+1;
        end
    end
end

task axi_write(input [5:0] address,input [31:0] value);
begin
    @(negedge ap_clk); awaddr=address;awvalid=1;
    @(posedge ap_clk); while(!awready) @(posedge ap_clk);
    @(negedge ap_clk); awvalid=0;wdata=value;wvalid=1;
    @(posedge ap_clk); while(!wready) @(posedge ap_clk);
    @(negedge ap_clk); wvalid=0;bready=1;
    @(posedge ap_clk); while(!bvalid) @(posedge ap_clk);
    if(bresp!=0) $fatal(1,"AXI write error");
    @(negedge ap_clk); bready=0;
end endtask

task axi_read(input [5:0] address,output [31:0] value);
begin
    @(negedge ap_clk); araddr=address;arvalid=1;
    @(posedge ap_clk); while(!arready) @(posedge ap_clk);
    @(negedge ap_clk); arvalid=0;rready=1;
    @(posedge ap_clk); while(!rvalid) @(posedge ap_clk);
    value=rdata;
    if(rresp!=0) $fatal(1,"AXI read error");
    @(negedge ap_clk); rready=0;
end endtask

initial begin
    if(!$value$plusargs("ROOT=%s",root)) $fatal(1,"ROOT not supplied");
    repeat(8) @(negedge ap_clk);
    ap_rst_n=1;
    repeat(8) @(negedge ap_clk);
    flist=$fopen({root,"/vectors/scenarios.txt"},"r");
    if(!flist) $fatal(1,"Cannot open scenario list");
    while(!$feof(flist)) begin
        rc=$fscanf(flist,"%s\n",name);
        if(rc==1) begin
            dir={root,"/rtl/",name};
            nin=0;nout=0;in_count=0;out_count=0;test_failed=0;gap_left=0;gap_used=0;
            fmeta=$fopen({root,"/vectors/",name,"/expected.txt"},"r");
            rc=$fscanf(fmeta,"%d %d %d %d",expected_h,expected_e,expected_tx,expected_c);
            $fclose(fmeta);
            if(rc!=4) $fatal(1,"Bad metadata %s",name);
            k=$fopen({root,"/vectors/",name,"/input.txt"},"r");
            while(!$feof(k)) begin
                rc=$fscanf(k,"%h %d\n",input_words[nin],input_last[nin]);
                if(rc==2) nin=nin+1;
            end
            $fclose(k);
            k=$fopen({root,"/vectors/",name,"/output.txt"},"r");
            while(!$feof(k)) begin
                rc=$fscanf(k,"%h %d\n",output_words[nout],output_last[nout]);
                if(rc==2) nout=nout+1;
            end
            $fclose(k);
            fin=$fopen({dir,"/input_handshakes.txt"},"w");
            fout=$fopen({dir,"/output_handshakes.txt"},"w");
            ftrace=$fopen({dir,"/cycles.csv"},"w");
            $fwrite(ftrace,"cycle,in_valid,in_ready,in_data,in_last,out_valid,out_ready,out_data,out_last,done\n");
            // No hardware reset between cases: activation code must clear status/configuration.
            axi_write(0,1);
            @(negedge ap_clk); start_cycle=cycle;active=1;
            timeout_cycle=cycle+100000;
            ctrl=0;
            while(!ctrl[1] && cycle<timeout_cycle) axi_read(0,ctrl);
            if(!ctrl[1]) $fatal(1,"Activation timed out: %s",name);
            done_cycle=cycle;
            axi_read(6'h10,observed_h);
            axi_read(6'h20,observed_e);
            axi_read(6'h30,observed_tx);
            // Keep the sentinel valid after done, proving that return does not drain it.
            repeat(20) @(negedge ap_clk);
            active=0;
            @(negedge ap_clk);
            if(in_count!=expected_c || out_count!=nout || observed_h!=expected_h || observed_e!=expected_e || observed_tx!=expected_tx)
                test_failed=1;
            fstatus=$fopen({dir,"/status.json"},"w");
            $fwrite(fstatus,"{\"halted\":%0d,\"error\":%0d,\"tx_id\":%0d,\"consumed\":%0d,\"output_words\":%0d,\"start_cycle\":%0d,\"done_cycle\":%0d,\"pass\":%s}\n",
                observed_h,observed_e,observed_tx,in_count,out_count,start_cycle,done_cycle,test_failed?"false":"true");
            $fclose(fstatus);
            fleft=$fopen({dir,"/unread.txt"},"w");
            for(j=in_count;j<nin;j=j+1) $fwrite(fleft,"%08x %0d\n",input_words[j],input_last[j]);
            $fclose(fleft);$fclose(fin);$fclose(fout);$fclose(ftrace);
            $display("PIN_RTL %s %s consumed=%0d expected=%0d output=%0d status=%0d/%0d/%0d",name,test_failed?"FAIL":"PASS",in_count,expected_c,out_count,observed_h,observed_e,observed_tx);
            tests=tests+1;
            failed=failed+test_failed;
            // On any interface error reset the physical stream path so subsequent diagnostics run.
            // Successful implementation needs no reset, including after protocol-error activations.
            if(test_failed) begin
                ap_rst_n=0;repeat(8) @(negedge ap_clk);ap_rst_n=1;repeat(8) @(negedge ap_clk);
            end
        end
    end
    $fclose(flist);
    $display("PIN_RTL_SUMMARY tests=%0d failures=%0d",tests,failed);
    if(failed || tests==0) $fatal(1,"Pin-level RTL verification failed");
    $finish;
end
initial begin
    #100000000;
    $fatal(1,"Global testbench timeout");
end
endmodule
