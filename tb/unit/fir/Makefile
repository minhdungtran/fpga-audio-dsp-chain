.DEFAULT_GOAL := sim

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(CURDIR)/../../..)

VERILOG_SOURCES += $(ROOT)/rtl/effects/fir.v

TOPLEVEL = fir
COCOTB_TEST_MODULES = test_fir

COEFF_SRC := $(ROOT)/coefficients/fir_8khz_63tap_q15.mem
COEFF_DST := $(CURDIR)/fir_8khz_63tap_q15.mem

$(COEFF_DST): $(COEFF_SRC)
	cp $< $@

export COCOTB_RESOLVE_X = ZEROS
export WAVES = 1

include $(shell cocotb-config --makefiles)/Makefile.sim
sim: $(COEFF_DST)