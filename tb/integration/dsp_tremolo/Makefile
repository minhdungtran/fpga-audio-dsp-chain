SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(ROOT)/rtl/top/dsp_tremolo.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_tx.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_rv.v
VERILOG_SOURCES += $(ROOT)/rtl/effects/amplifier.v
VERILOG_SOURCES += $(ROOT)/rtl/effects/tremolo_lfo.v


TOPLEVEL = dsp_tremolo

MODULE = test_tremolo

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim