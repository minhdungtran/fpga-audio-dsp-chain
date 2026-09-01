module dual_port_ram
#(
    parameter WIDTH = 64,
    parameter ADDR_WIDTH = 3,
    parameter PTR_WIDTH = ADDR_WIDTH+1
)
(
    input wire wr_clk,
    input wire rd_clk,
    input wire wr_en,
    input wire rd_en,
    input wire full,
    input wire empty,
    input wire [PTR_WIDTH-1:0] cur_rd_bptr,
    input wire [PTR_WIDTH-1:0] cur_wr_bptr,
    input wire [WIDTH-1:0] d_in,

    output reg [WIDTH-1:0] d_out
);
localparam DEPTH = 1 << ADDR_WIDTH;

reg [WIDTH-1:0] ram [0:DEPTH-1];

always @(posedge wr_clk) begin
    if (wr_en & !full) begin
        ram[cur_wr_bptr[ADDR_WIDTH-1:0]] <= d_in;
    end
end

always @(posedge rd_clk) begin
    if (rd_en & !empty) begin
        d_out <= ram[cur_rd_bptr[ADDR_WIDTH-1:0]];
    end
end

endmodule

