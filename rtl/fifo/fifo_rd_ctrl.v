module fifo_rd_ctrl
#(
    parameter WIDTH = 64,
    parameter ADDR_WIDTH = 3,
    parameter PTR_WIDTH = ADDR_WIDTH +1
)
(
    input wire rd_reset,
    input wire rd_clk,
    input wire rd_en,
    input wire [PTR_WIDTH-1:0] sync_wr_gptr,

    output reg empty,
    output reg [PTR_WIDTH-1:0] cur_rd_bptr,
    output reg [PTR_WIDTH-1:0] cur_rd_gptr
);

localparam DEPTH = 1<<ADDR_WIDTH;

wire [PTR_WIDTH-1:0] next_rd_bptr;
wire [PTR_WIDTH-1:0] next_rd_gptr;

wire next_empty;
wire rd_valid;

assign rd_valid = (~empty) & (rd_en);
assign next_rd_bptr = cur_rd_bptr + {{(PTR_WIDTH-1){1'b0}},rd_valid};
assign next_rd_gptr = (next_rd_bptr>>1) ^ next_rd_bptr;
assign next_empty = (sync_wr_gptr == next_rd_gptr);

always @(posedge rd_clk or posedge rd_reset) begin
    if (rd_reset) begin
        cur_rd_bptr <= 0;
        cur_rd_gptr <= 0;
        empty <= 1;
    end
    else begin
        cur_rd_bptr <= next_rd_bptr;
        cur_rd_gptr <= next_rd_gptr;
        empty <= next_empty;
        
    end
end 
endmodule



