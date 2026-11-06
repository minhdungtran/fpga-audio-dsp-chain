SIM ?= verilator
TOPLEVEL_LANG ?= verilog

PROJECT_ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/amplifier.sv

TOPLEVEL = amplifier
COCOTB_TEST_MODULES = test_amp

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim