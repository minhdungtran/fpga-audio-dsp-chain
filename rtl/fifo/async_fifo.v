module async_fifo
#(
    parameter WIDTH = 64,
    parameter ADDR_WIDTH = 3,
    parameter PTR_WIDTH = ADDR_WIDTH + 1
)
(
    input wire rd_clk, rd_reset, rd_en,
    input wire wr_clk, wr_reset, wr_en,
    input wire [WIDTH-1:0] d_in,

    output wire empty, full,
    output wire [WIDTH-1:0] d_out
);

wire [PTR_WIDTH-1:0] in_sync_r_w;
wire [PTR_WIDTH-1:0] out_sync_r_w;

wire [PTR_WIDTH-1:0] in_sync_w_r;
wire [PTR_WIDTH-1:0] out_sync_w_r;

wire [PTR_WIDTH-1:0] wr_bptr;
wire [PTR_WIDTH-1:0] rd_bptr;



synchronizer #(
    .WIDTH(WIDTH),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(PTR_WIDTH)
) r_w(
    .clk(wr_clk),
    .reset(wr_reset),
    .d_in(in_sync_r_w),

    .q_2(out_sync_r_w)
);

synchronizer #(
    .WIDTH(WIDTH),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(PTR_WIDTH)
) w_r(
    .clk(rd_clk),
    .reset(rd_reset),
    .d_in(in_sync_w_r),

    .q_2(out_sync_w_r)
);

fifo_rd_ctrl #(
    .WIDTH(WIDTH),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(PTR_WIDTH)
)read(
    .rd_reset(rd_reset),
    .rd_clk(rd_clk),
    .rd_en(rd_en),
    .sync_wr_gptr(out_sync_w_r),
    .empty(empty),
    .cur_rd_bptr(rd_bptr),
    .cur_rd_gptr(in_sync_r_w)
);

fifo_wr_ctrl #(
    .WIDTH(WIDTH),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(PTR_WIDTH)
)write(
    .wr_en(wr_en),
    .wr_reset(wr_reset),
    .wr_clk(wr_clk),
    .sync_rd_gptr(out_sync_r_w),
    .full(full),
    .cur_wr_gptr(in_sync_w_r),
    .cur_wr_bptr(wr_bptr)
);

dual_port_ram #(
    .WIDTH(WIDTH),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(PTR_WIDTH)
)dual_port_ram(
    .wr_clk(wr_clk),
    .rd_clk(rd_clk),
    .wr_en(wr_en),
    .rd_en(rd_en),
    .full(full),
    .empty(empty),
    .cur_rd_bptr(rd_bptr),
    .cur_wr_bptr(wr_bptr),
    .d_in(d_in),
    .d_out(d_out)
);

endmodule