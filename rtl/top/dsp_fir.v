
module dsp_fir
#(
    parameter WIDTH = 24,
    parameter WIDTH_SLOT = 32,
    parameter COEFFICIENT_WIDTH = 16,
    parameter FRAC_BITS = 15,
    parameter NUM_TAPS = 63
)
(
    input wire                top_i2s_clk, top_dsp_clk,      
    input wire                top_i2s_reset, top_dsp_reset,
    input wire                top_WS,        
    input wire                top_in_SD,        

    output wire               top_out_SD
       
);
localparam PADDING = WIDTH_SLOT - WIDTH;
localparam FIFO_WIDTH = 2 * WIDTH_SLOT;

// FIR's wires
reg [WIDTH-1:0] fir_in_LD, fir_in_RD;
wire [WIDTH-1:0] fir_out_LD, fir_out_RD;
reg fir_in_valid;
wire fir_out_valid;

// Receiver and fifo 1's wires
wire [WIDTH-1:0] rv_LD;
wire [WIDTH-1:0] rv_RD;
wire rv_out_rd;
wire empty_1, full_1;
reg fifo1_rd_en;
wire [2*WIDTH_SLOT-1:0] fifo1_d_in, fifo1_d_out;
assign fifo1_d_in = {
    {{PADDING{rv_LD[WIDTH-1]}}, rv_LD},
    {{PADDING{rv_RD[WIDTH-1]}}, rv_RD}
};
// FIR and fifo 2's wires
wire [WIDTH_SLOT*2-1:0] fifo2_d_in;
assign fifo2_d_in = {
  {{PADDING{fir_out_LD[WIDTH-1]}}, fir_out_LD},
  {{PADDING{fir_out_RD[WIDTH-1]}}, fir_out_RD}
};
wire [WIDTH_SLOT*2-1:0] fifo2_d_out;

// Fifo 2 and transmitter's wires
reg [WIDTH-1:0] tx_LD, tx_RD;
wire empty_2, full_2;
reg fifo2_rd_en;
reg tx_in_ready;

// State for FSM
reg [1:0] state_1;
reg [1:0] state_2;

localparam IDLE       = 2'd0;
localparam FIFO_OUT   = 2'd1;
localparam LOAD_FRAME = 2'd2;
localparam WAIT_FIR   = 2'd3;


// FSM for receiver -> fifo -> fir
always @(posedge top_dsp_clk) begin
    if (top_dsp_reset) begin
        fifo1_rd_en <= 0;
        fir_in_valid <= 0;
        fir_in_LD <= 0;
        fir_in_RD <= 0;
        state_1 <= IDLE;
    end else begin

      fir_in_valid <= 0;
      fifo1_rd_en <= 0;
  
      case (state_1)
  
          IDLE: begin
              if (!empty_1) begin
                  fifo1_rd_en <= 1;
                  state_1 <= FIFO_OUT;
              end
          end
  
          FIFO_OUT: begin
              state_1 <= LOAD_FRAME;
          end
  
          LOAD_FRAME: begin
              fir_in_LD <= $signed(fifo1_d_out[WIDTH_SLOT + WIDTH - 1 : WIDTH_SLOT]);
              fir_in_RD <= $signed(fifo1_d_out[WIDTH-1:0]);
              fir_in_valid <= 1;
              state_1 <= WAIT_FIR;
          end
  
          WAIT_FIR: begin
              if (fir_out_valid) begin
                  state_1 <= IDLE;
              end
          end
  
          default: begin
              state_1 <= IDLE;
          end
      endcase
    end
end

// FSM for fir -> fifo -> transmitter
always @(posedge top_i2s_clk) begin
    if (top_i2s_reset) begin
        fifo2_rd_en <= 0;
        tx_in_ready <= 0;  
        tx_LD <= 0;
        tx_RD <= 0;
        state_2 <= IDLE;
    end
    else begin
        fifo2_rd_en <= 0;
        tx_in_ready <= 0;
        case (state_2) 
            IDLE: begin
              if (!empty_2) begin
                fifo2_rd_en <= 1;
                state_2 <= FIFO_OUT;
              end
            end
            FIFO_OUT: begin
                state_2 <= LOAD_FRAME;
            end
            LOAD_FRAME: begin
                tx_LD <= $signed(fifo2_d_out[WIDTH_SLOT+WIDTH-1:WIDTH_SLOT]);
                tx_RD <= $signed(fifo2_d_out[WIDTH-1:0]);
                tx_in_ready <= 1;
                state_2 <= IDLE;
            end
        endcase
    end
end
i2s_rv #(
    .WIDTH(WIDTH)
) receiver(
    .sck(top_i2s_clk),
    .WS(top_WS),
    .SD(top_in_SD),
    .reset(top_i2s_reset),
    .data_ready(rv_out_rd),
    .output_LD(rv_LD),
    .output_RD(rv_RD)
);

async_fifo #(
    .WIDTH(FIFO_WIDTH)
) u_fifo1(
    .rd_clk(top_dsp_clk),
    .rd_reset(top_dsp_reset),
    .rd_en(fifo1_rd_en),
    .wr_clk(top_i2s_clk),
    .wr_reset(top_i2s_reset),
    .wr_en(rv_out_rd),
    .d_in(fifo1_d_in),
    .empty(empty_1),
    .full(full_1),
    .d_out(fifo1_d_out)
);

fir #(
    .WIDTH(WIDTH),
    .COEFFICIENT_WIDTH(COEFFICIENT_WIDTH),
    .FRAC_BITS(FRAC_BITS),
    .NUM_TAPS(NUM_TAPS)
) u_fir(
    .data_valid(fir_in_valid),
    .data_ready(fir_out_valid),
    .clk(top_dsp_clk),
    .reset(top_dsp_reset),
    .in_LD(fir_in_LD),
    .in_RD(fir_in_RD),
    .out_LD(fir_out_LD),
    .out_RD(fir_out_RD)
);

async_fifo #(
    .WIDTH(FIFO_WIDTH)
) u_fifo2(
    .rd_clk(top_i2s_clk),
    .rd_reset(top_i2s_reset),
    .rd_en(fifo2_rd_en),
    .wr_clk(top_dsp_clk),
    .wr_reset(top_dsp_reset),
    .wr_en(fir_out_valid),
    .d_in(fifo2_d_in),
    .empty(empty_2),
    .full(full_2),
    .d_out(fifo2_d_out)
);

i2s_tx #(
    .WIDTH(WIDTH)
) transmitter(
    .sck(top_i2s_clk),
    .WS(top_WS),
    .input_LD(tx_LD),
    .input_RD(tx_RD),
    .reset(top_i2s_reset),
    .data_valid(tx_in_ready),
    .SD(top_out_SD)
);
endmodule