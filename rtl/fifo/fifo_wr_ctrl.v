module fifo_wr_ctrl
#(
    parameter WIDTH = 64,
    parameter ADDR_WIDTH = 3,
    parameter PTR_WIDTH = ADDR_WIDTH + 1
)
(
    input wire wr_en,
    input wire wr_reset,
    input wire wr_clk,
    input wire [PTR_WIDTH-1:0] sync_rd_gptr,

    output reg full,
    output reg [PTR_WIDTH-1:0] cur_wr_gptr,
    output reg [PTR_WIDTH-1:0] cur_wr_bptr
);

localparam DEPTH = 1<<ADDR_WIDTH;

wire [PTR_WIDTH-1:0] next_wr_gptr;
wire [PTR_WIDTH-1:0] next_wr_bptr;

wire next_full;
wire wr_valid;

assign wr_valid = (wr_en) & (~full);
assign next_wr_bptr = (cur_wr_bptr) + {{(PTR_WIDTH-1){1'b0}}, wr_valid};
assign next_wr_gptr = (next_wr_bptr >> 1) ^ next_wr_bptr;
assign next_full = (next_wr_gptr == {~sync_rd_gptr[PTR_WIDTH-1:PTR_WIDTH-2],sync_rd_gptr[PTR_WIDTH-3:0]});


always @(posedge wr_clk or posedge wr_reset) begin
    if (wr_reset) begin
        cur_wr_bptr <= 0;
        cur_wr_gptr <= 0;
        full <= 0;
    end

    else begin
        full <= next_full;
        cur_wr_bptr <= next_wr_bptr;
        cur_wr_gptr <= next_wr_gptr;    
    end  
end
endmodule
