SIM ?= verilator
TOPLEVEL_LANG ?= verilog

PROJECT_ROOT := $(abspath $(PWD)/../../..)

MEM_SOURCE := $(PROJECT_ROOT)/coefficients/reverb/mem
MEM_TARGET := $(PWD)/coefficients/reverb/mem

$(MEM_TARGET):
	mkdir -p $(MEM_TARGET)

.PHONY: prepare-mem
prepare-mem: | $(MEM_TARGET)
	cp $(MEM_SOURCE)/comb_*_g.mem $(MEM_TARGET)/

sim: prepare-mem

VERILOG_SOURCES += $(wildcard $(PROJECT_ROOT)/rtl/async_fifo/rtl/*.sv)
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/top/dsp_reverb.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/i2s/i2s_tx.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/i2s/i2s_rx.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/memory/audio_bram.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/room_lut.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/comb_filter.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/all_pass_filter.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/mix.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/reverb.sv

TOPLEVEL = dsp_reverb

COCOTB_TEST_MODULES = test_dsp_reverb

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1
EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim