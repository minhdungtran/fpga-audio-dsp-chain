.DEFAULT_GOAL := sim

SIM ?= verilator
TOPLEVEL_LANG ?= verilog

PROJECT_ROOT := $(abspath $(CURDIR)/../../..)

VERILOG_SOURCES += $(wildcard $(PROJECT_ROOT)/rtl/async_fifo/rtl/*.sv)
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/top/dsp_chain.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/i2s/i2s_tx.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/i2s/i2s_rx.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/memory/audio_bram.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/fir.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/delay.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/amplifier.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/reverb.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/room_lut.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/comb_filter.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/all_pass_filter.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/mix.sv


TOPLEVEL = dsp_chain
COCOTB_TEST_MODULES  = test_dsp_chain

# FIR coefficient ROM files
MEM_SOURCE_FIR := $(PROJECT_ROOT)/coefficients/fir/mem
MEM_TARGET_FIR := $(CURDIR)/coefficients/fir/mem

MEM_SOURCE_REVERB := $(PROJECT_ROOT)/coefficients/reverb/mem
MEM_TARGET_REVERB := $(CURDIR)/coefficients/reverb/mem

.PHONY: prepare-mem

prepare-mem:
	mkdir -p $(MEM_TARGET_FIR)
	mkdir -p $(MEM_TARGET_REVERB)

	cp $(MEM_SOURCE_FIR)/fir_*_q15.mem $(MEM_TARGET_FIR)/
	cp $(MEM_SOURCE_REVERB)/comb_*_g.mem $(MEM_TARGET_REVERB)/


sim: prepare-mem

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim