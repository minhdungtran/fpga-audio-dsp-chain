module audio_bram 
#(
    parameter WIDTH = 24,
    parameter DEPTH = 24000,
    parameter ADDR_WIDTH = $clog2(DEPTH)
)
(
    output logic [WIDTH-1:0]     rd_data,
    input logic [ADDR_WIDTH-1:0] rd_addr,

    input logic                  clk,

    input logic [WIDTH-1:0]      wr_data,
    input logic [ADDR_WIDTH-1:0] wr_addr,
    input logic                  wr_en
);

(*ram_style = "block"*)
logic signed [WIDTH-1:0] memory [0:DEPTH-1];

always_ff @(posedge clk) begin
    rd_data <= memory[rd_addr];

    if (wr_en) begin
        memory[wr_addr] <= wr_data;
    end
end
endmodule
    

