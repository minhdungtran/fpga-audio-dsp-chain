.DEFAULT_GOAL := sim

SIM ?= icarus
TOPLEVEL_LANG ?= verilog

ROOT := $(abspath $(CURDIR)/../../..)

VERILOG_SOURCES += $(wildcard $(ROOT)/rtl/fifo/*.v)
VERILOG_SOURCES += $(ROOT)/rtl/top/dsp_chain.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_tx.v
VERILOG_SOURCES += $(ROOT)/rtl/i2s/i2s_rv.v
VERILOG_SOURCES += $(ROOT)/rtl/effects/fir.v
VERILOG_SOURCES += $(ROOT)/rtl/effects/amplifier.v
VERILOG_SOURCES += $(ROOT)/rtl/effects/tremolo_lfo.v


TOPLEVEL = dsp_chain
MODULE = test_dsp_chain

COEFF_SRC := $(ROOT)/coefficients/fir_8khz_63tap_q15.mem
COEFF_DST := $(CURDIR)/fir_8khz_63tap_q15.mem

$(COEFF_DST): $(COEFF_SRC)
	cp $< $@

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1

include $(shell cocotb-config --makefiles)/Makefile.sim
sim: $(COEFF_DST)