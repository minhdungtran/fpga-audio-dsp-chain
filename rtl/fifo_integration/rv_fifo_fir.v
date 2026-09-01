module rv_fifo_fir
#(
    parameter WIDTH = 24,
    parameter WIDTH_SLOT = 32
)
(
    input wire top_i2s_clk, top_dsp_clk,
    input wire top_WS,
    input wire top_SD,
    input wire top_i2s_reset, top_dsp_reset,

    output wire top_data_ready,
    output wire [WIDTH-1:0] top_out_LD,
    output wire [WIDTH-1:0] top_out_RD
);

localparam PADDING = WIDTH_SLOT - WIDTH;
localparam FIFO_WIDTH = WIDTH_SLOT*2;

wire rv_ready_fifo;
wire empty, full;

wire [WIDTH-1:0] rx_LD;
wire [WIDTH-1:0] rx_RD;

wire [FIFO_WIDTH-1:0] fifo_d_in;
wire [FIFO_WIDTH-1:0] fifo_d_out;
assign fifo_d_in = {
    {{PADDING{rx_LD[WIDTH-1]}}, rx_LD},
    {{PADDING{rx_RD[WIDTH-1]}}, rx_RD}
};

reg [WIDTH-1:0] fir_LD;
reg [WIDTH-1:0] fir_RD;

reg fifo_rd_en;
reg fir_in_valid;
wire fir_out_valid;

assign top_data_ready = fir_out_valid;

reg [1:0] state;
localparam WAIT_FRAME = 2'd0;
localparam FIFO_OUT   = 2'd1;
localparam LOAD_FRAME = 2'd2;
localparam WAIT_FIR   = 2'd3;


always @(posedge top_dsp_clk) begin
    if (top_dsp_reset) begin
        fifo_rd_en <= 0;
        fir_in_valid <= 0;
        fir_LD <= 0;
        fir_RD <= 0;
        state <= WAIT_FRAME;
    end else begin

      fir_in_valid <= 0;
      fifo_rd_en <= 0;
  
      case (state)
  
          WAIT_FRAME: begin
              if (!empty) begin
                  fifo_rd_en <= 1;
                  state <= FIFO_OUT;
              end
          end
  
          FIFO_OUT: begin
              state <= LOAD_FRAME;
          end
  
          LOAD_FRAME: begin
              fir_LD <= $signed(fifo_d_out[WIDTH_SLOT + WIDTH - 1 : WIDTH_SLOT]);
              fir_RD <= $signed(fifo_d_out[WIDTH-1:0]);
              fir_in_valid <= 1;
              state <= WAIT_FIR;
          end
  
          WAIT_FIR: begin
              if (fir_out_valid) begin
                  state <= WAIT_FRAME;
              end
          end
  
          default: begin
              state <= WAIT_FRAME;
          end
      endcase
    end
end
  
i2s_rv #(
    .WIDTH(WIDTH)
) u_receiver(
    .sck(top_i2s_clk),
    .WS(top_WS),   
    .SD(top_SD),     
    .reset(top_i2s_reset),    
    .data_ready(rv_ready_fifo),
    .output_LD(rx_LD),
    .output_RD(rx_RD)
);


async_fifo #(
    .WIDTH(FIFO_WIDTH)
) u_fifo(
    .rd_clk(top_dsp_clk),
    .rd_reset(top_dsp_reset),
    .rd_en(fifo_rd_en),
    .wr_clk(top_i2s_clk),
    .wr_reset(top_i2s_reset),
    .wr_en(rv_ready_fifo),
    .d_in(fifo_d_in),
    .empty(empty),
    .full(full),
    .d_out(fifo_d_out)
);

fir #(
    .WIDTH(WIDTH)
) u_fir(
    .clk(top_dsp_clk),
    .reset(top_dsp_reset),
    .data_valid(fir_in_valid),
    .in_LD(fir_LD),
    .in_RD(fir_RD),
    .out_LD(top_out_LD),
    .out_RD(top_out_RD),
    .data_ready(fir_out_valid)
);

endmodule