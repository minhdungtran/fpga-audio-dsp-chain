SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(ROOT)/rtl/effects/tremolo_lfo.v

TOPLEVEL = tremolo_lfo

MODULE = test_lfo

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim