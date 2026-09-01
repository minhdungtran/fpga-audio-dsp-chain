module synchronizer
#(
    parameter WIDTH = 64,
    parameter ADDR_WIDTH = 3,
    parameter PTR_WIDTH = ADDR_WIDTH +1
)
(
    input wire clk,
    input wire reset,
    input wire [PTR_WIDTH-1:0] d_in,
    output reg [PTR_WIDTH-1:0] q_2
);

reg [PTR_WIDTH-1:0] q_1;

always @(posedge(clk) or posedge reset) begin
    if (reset) begin
        q_1 <= 0;
        q_2 <= 0;
    end
    else begin 
      q_1 <= d_in;
      q_2 <= q_1;
    end
end
endmodule
