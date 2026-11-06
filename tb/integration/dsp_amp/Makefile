SIM ?= verilator
TOPLEVEL_LANG ?= verilog

PROJECT_ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/top/dsp_amp.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/i2s/i2s_tx.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/i2s/i2s_rx.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/amplifier.sv


TOPLEVEL = dsp_amp

MODULE = test_dsp_amp

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim