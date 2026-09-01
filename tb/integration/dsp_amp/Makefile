SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(ROOT)/rtl/top/dsp_amp.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_tx.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_rv.v
VERILOG_SOURCES += $(ROOT)/rtl/effects/amplifier.v


TOPLEVEL = dsp_amp

MODULE = test_dsp_amp

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim