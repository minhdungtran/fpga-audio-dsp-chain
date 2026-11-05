SIM ?= verilator
TOPLEVEL_LANG ?= verilog

COMB_ID ?= 0

export TEST_COMB_ID := $(COMB_ID)

PROJECT_ROOT := $(abspath $(PWD)/../../..)

G_MEM_FILE := $(PROJECT_ROOT)/coefficients/reverb/mem/comb_$(COMB_ID)_g.mem

VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/memory/audio_bram.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/room_lut.sv
VERILOG_SOURCES += $(PROJECT_ROOT)/rtl/effects/reverb/comb_filter.sv

COMPILE_ARGS += -GCOMB_ID=$(COMB_ID)
COMPILE_ARGS += -GG_MEM_FILE='"$(G_MEM_FILE)"'

SIM_BUILD = sim_build/comb_$(COMB_ID)

CUSTOM_COMPILE_DEPS += $(G_MEM_FILE)

TOPLEVEL = comb_filter

COCOTB_TEST_MODULES  = test_comb_filter

export COCOTB_RESOLVE_X=ZEROS
export WAVES=1
EXTRA_ARGS += --trace --trace-fst --trace-structs

include $(shell cocotb-config --makefiles)/Makefile.sim