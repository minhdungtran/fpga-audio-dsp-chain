module fir_fifo_tx
#(
    parameter WIDTH = 24,
    parameter WIDTH_SLOT = 32
)
(   
    input wire top_i2s_clk, top_dsp_clk,
    input wire top_WS,
    input wire top_i2s_reset, top_dsp_reset,
    input wire top_fir_in_valid,
    input wire [WIDTH-1:0] in_LD, in_RD,
    output reg top_SD
);
localparam PADDING = WIDTH_SLOT - WIDTH;
localparam FIFO_WIDTH = 2 * WIDTH_SLOT;


wire [WIDTH-1:0] fir_out_LD, fir_out_RD;
wire [WIDTH_SLOT*2-1:0] in_fifo;
assign in_fifo = {
  {{PADDING{fir_out_LD[WIDTH-1]}}, fir_out_LD},
  {{PADDING{fir_out_RD[WIDTH-1]}}, fir_out_RD}
};

wire [WIDTH_SLOT*2-1:0] out_fifo;
reg [WIDTH-1:0] fifo_out_LD, fifo_out_RD;

wire empty, full;
wire fir_out_valid;
reg fifo_rd_en;
reg tx_in_ready;

reg [1:0] state;
localparam IDLE = 2'd0;
localparam FIFO_OUT = 2'd1;
localparam LOAD_FRAME = 2'd2;

always @(posedge top_i2s_clk) begin
    if (top_i2s_reset) begin
        fifo_rd_en <= 0;
        tx_in_ready <= 0;  
        fifo_out_LD <= 0;
        fifo_out_RD <= 0;
        state <= IDLE;
    end
    else begin
        fifo_rd_en <= 0;
        tx_in_ready <= 0;
        case (state) 
            IDLE: begin
              if (!empty) begin
                fifo_rd_en <= 1;
                state <= FIFO_OUT;
              end
            end
            FIFO_OUT: begin
                state <= LOAD_FRAME;
            end
            LOAD_FRAME: begin
                fifo_out_LD <= $signed(out_fifo[WIDTH_SLOT+WIDTH-1:WIDTH_SLOT]);
                fifo_out_RD <= $signed(out_fifo[WIDTH-1:0]);
                tx_in_ready <= 1;
                state <= IDLE;
            end
        endcase
    end
end

fir #(
    .WIDTH(WIDTH)
) u_fir (
    .clk(top_dsp_clk),
    .reset(top_dsp_reset),
    .data_valid(top_fir_in_valid),
    .in_LD(in_LD),
    .in_RD(in_RD),
    .out_LD(fir_out_LD),
    .out_RD(fir_out_RD),
    .data_ready(fir_out_valid)
);

async_fifo #(
    .WIDTH(FIFO_WIDTH)
) u_fifo(
    .rd_clk(top_i2s_clk),
    .rd_reset(top_i2s_reset),
    .rd_en(fifo_rd_en),
    .wr_clk(top_dsp_clk),
    .wr_reset(top_dsp_reset),
    .wr_en(fir_out_valid),
    .d_in(in_fifo),
    .empty(empty),
    .full(full),
    .d_out(out_fifo)
);

i2s_tx  #(
    .WIDTH(WIDTH)
) u_transmitter (
    .sck(top_i2s_clk),
    .reset(top_i2s_reset),
    .WS(top_WS),
    .data_valid(tx_in_ready),
    .input_LD(fifo_out_LD),
    .input_RD(fifo_out_RD),
    .SD(top_SD)
);

endmodule