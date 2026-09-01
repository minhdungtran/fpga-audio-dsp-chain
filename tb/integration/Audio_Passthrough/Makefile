SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(ROOT)/rtl/top/Audio_Passthrough.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_tx.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_rv.v


TOPLEVEL = Audio_Passthrough

MODULE = test_AP

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim