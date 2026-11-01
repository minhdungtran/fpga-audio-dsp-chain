SIM ?= verilator
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(wildcard $(ROOT)/rtl/async_fifo/rtl/*.sv)
VERILOG_SOURCES += $(ROOT)/rtl/top/dsp_delay.sv
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_tx.sv
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_rx.sv
VERILOG_SOURCES += $(ROOT)/rtl/effects/delay.sv
VERILOG_SOURCES += $(ROOT)/rtl/memory/audio_bram.sv

TOPLEVEL = dsp_delay

MODULE = test_dsp_delay

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1
EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim