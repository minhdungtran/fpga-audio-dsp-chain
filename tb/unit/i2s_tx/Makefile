SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(PWD)/../../..)

VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_tx.v

TOPLEVEL = i2s_tx

MODULE = test_i2s_tx

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim