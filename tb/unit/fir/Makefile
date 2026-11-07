.DEFAULT_GOAL := sim

SIM ?= verilator
TOPLEVEL_LANG ?= verilog

PROJECT_ROOT := $(abspath $(CURDIR)/../../..)

VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/fir.sv

TOPLEVEL = fir
COCOTB_TEST_MODULES = test_fir

# FIR coefficient ROM files
MEM_SOURCE := $(PROJECT_ROOT)/coefficients/fir/mem
MEM_TARGET := $(CURDIR)/coefficients/fir/mem

.PHONY: prepare-mem

prepare-mem:
	mkdir -p $(MEM_TARGET)
	cp $(MEM_SOURCE)/fir_*_q15.mem $(MEM_TARGET)/

sim: prepare-mem

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim
