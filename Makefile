SIM ?= verilator

TEST_MAKEFILES := $(shell find tb -type f -name Makefile )
TEST_DIRS := $(patsubst %/Makefile,%,$(TEST_MAKEFILES))

RTL_FILES := $(shell find rtl -type f -name "*.v")

.PHONY: help lint test clean all

help:	
	@echo "Available targets:"
	@echo "make lint"
	@echo "make test"
	@echo "make clean"

lint:
	verilator --lint-only --Wall -Wno-MULTITOP -Wno-fatal $(RTL_FILES)

test: 
	@echo "Simulator: $(SIM)"
	@for dir in $(TEST_DIRS); do \
	    @echo "Test in $$dir"; \
		$(MAKE) -C $$dir SIM=$(SIM); \
	done	

clean: 
	@echo "Cleaning"
	@for dir in $(TEST_DIRS); do \
		@echo "Clean in $$dir"; \
		$(MAKE) -C $$dir clean; \
	done

all: lint test
