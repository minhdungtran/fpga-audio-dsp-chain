SIM ?= icarus
TOPLEVEL_LANG ?= verilog

VERILOG_SOURCES += $(PWD)/../../../rtl/effects/amplifier.v

TOPLEVEL = amplifier

MODULE = test_amp

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim