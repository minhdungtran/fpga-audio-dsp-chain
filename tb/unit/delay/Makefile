SIM ?= verilator
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../../rtl/memory/audio_bram.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/effects/delay.sv


TOPLEVEL = delay

COCOTB_TEST_MODULES  = test_delay

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1
EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim