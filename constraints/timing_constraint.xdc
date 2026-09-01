create_clock -period 20.000 -name dsp_clk [get_ports top_dsp_clk]

create_clock -period 325.520 -name i2s_clk [get_ports top_i2s_clk]

set_clock_groups -asynchronous -group [get_clocks dsp_clk] -group [get_clocks i2s_clk]