set root [file dirname [file normalize [info script]]]
cd $root
set stage $::env(MATVEC_STAGE)
if {$stage eq "csim"} {
    open_project -reset hls_proj
    set_top matvec
    add_files [file join $root gen matvec.cpp] -cflags "-I$root"
    add_files -tb [file join $root matvec_tb.cpp] -cflags "-I$root"
    if {[file exists [file join $root include streamutils.cpp]]} {
        add_files -tb [file join $root include streamutils.cpp] -cflags "-I$root"
    }
    open_solution -reset solution1
    set_part {xc7z020clg484-1}
    create_clock -period 10
    csim_design -clean -argv "[file join $root evidence vectors] csim"
} elseif {$stage eq "synth"} {
    open_project hls_proj
    open_solution solution1
    csynth_design
} elseif {$stage eq "cosim"} {
    open_project hls_proj
    open_solution solution1
    cosim_design -rtl verilog -tool xsim -trace_level all -argv "[file join $root evidence vectors] cosim"
} else { error "Unknown MATVEC_STAGE: $stage" }
puts "MATVEC_STAGE_PASSED $stage"
exit 0
