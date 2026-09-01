module dsp_chain
#(
    parameter WIDTH = 24,
    parameter G_LENGTH = 16,
    parameter WIDTH_SLOT = 32,
    parameter COEFFICIENT_WIDTH = 16,
    parameter FRAC_BITS = 15,
    parameter NUM_TAPS = 63
)
(
    input wire top_i2s_clk, top_dsp_clk,      
    input wire top_i2s_reset, top_dsp_reset,
    
    input wire top_WS,        
    input wire top_in_SD,   

    // Effects control
    input wire amp_en,
    input wire fir_en,
    input wire trem_en,

    // Gain configuration
    input wire [G_LENGTH-1:0] gain_value,
    
    // Tremolo configuration
    input wire [15:0]         control_rate,
    input wire [13:0]         control_depth, 

    output wire               top_out_SD
);

localparam PADDING = WIDTH_SLOT - WIDTH;
localparam FIFO_WIDTH = 2 * WIDTH_SLOT;


// Amplifier's wires
reg [WIDTH-1:0] amp_in_LD, amp_in_RD;
wire [WIDTH-1:0] amp_out_LD, amp_out_RD;
reg amp_in_valid;
wire amp_out_valid;

// FIR's wires
reg [WIDTH-1:0] fir_in_LD, fir_in_RD;
wire [WIDTH-1:0] fir_out_LD, fir_out_RD;
reg fir_in_valid;
wire fir_out_valid;

// Tremolo's wires
reg [WIDTH-1:0] trem_in_LD, trem_in_RD;
wire [WIDTH-1:0] trem_out_LD, trem_out_RD;
wire [WIDTH-1:0] lfo_out_LD, lfo_out_RD;
wire [FRAC_BITS:0] trem_gain;
reg trem_in_valid;
wire lfo_out_valid;
wire trem_out_valid;

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
reg [WIDTH_SLOT*2-1:0] fifo2_d_in;
wire [WIDTH_SLOT*2-1:0] fifo2_d_out;

// Fifo 2 and transmitter's wires
reg [WIDTH-1:0] tx_LD, tx_RD;
wire empty_2, full_2;
reg fifo2_rd_en;
reg tx_in_ready;

// DSP chain control
reg active_amp_en;
reg active_fir_en;
reg active_trem_en;

reg [15:0] control_rate_active;
reg [13:0] control_depth_active;
reg [G_LENGTH-1:0] gain_active;

// State for FSM
reg [2:0] state_1;
reg [2:0] state_2;

localparam IDLE               = 3'd0;
localparam FIFO_OUT           = 3'd1;
localparam LOAD_FRAME         = 3'd2;
localparam EFFECT_GAIN        = 3'd3;
localparam EFFECT_FIR         = 3'd4;
localparam EFFECT_TREMOLO     = 3'd5;
localparam WRITE_OUTPUT       = 3'd6;

// FSM for receiver -> fifo -> fir
always @(posedge top_dsp_clk) begin
    if (top_dsp_reset) begin

        active_amp_en <= amp_en;
        active_trem_en <= trem_en;
        active_fir_en <= fir_en;

        control_depth_active <= control_depth;
        control_rate_active <= control_rate;
        gain_active <= gain_value;

        fifo1_rd_en <= 0;
        fir_in_valid <= 0;
        amp_in_valid <= 0;
        trem_in_valid <= 0;

        fir_in_LD <= 0;
        fir_in_RD <= 0;
        amp_in_LD <= 0;
        amp_in_RD <= 0;
        trem_in_LD <= 0;
        trem_in_RD <= 0;

        state_1 <= IDLE;
    end else begin

      fir_in_valid <= 0;
      amp_in_valid <= 0;
      trem_in_valid <= 0;
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
              amp_in_LD <= $signed(fifo1_d_out[WIDTH_SLOT + WIDTH - 1 : WIDTH_SLOT]);
              amp_in_RD <= $signed(fifo1_d_out[WIDTH-1:0]);
              amp_in_valid <= 1;
              state_1 <= EFFECT_GAIN;
          end
  
          EFFECT_GAIN: begin
              if (amp_out_valid) begin
                fir_in_LD  <= active_amp_en ? amp_out_LD : amp_in_LD;
                fir_in_RD <= active_amp_en ? amp_out_RD : amp_in_RD;
                fir_in_valid <= 1;
                state_1 <= EFFECT_FIR;
              end
          end

          EFFECT_FIR: begin
            if (fir_out_valid) begin
                trem_in_LD <= active_fir_en ? fir_out_LD : fir_in_LD;
                trem_in_RD <= active_fir_en ? fir_out_RD : fir_in_RD;
                trem_in_valid <= 1;
                state_1 <= EFFECT_TREMOLO;
            end
          end

          EFFECT_TREMOLO: begin
            if (trem_out_valid) begin
              if (active_trem_en) begin
                fifo2_d_in <= {{{PADDING{trem_out_LD[WIDTH-1]}}, trem_out_LD},{{PADDING{trem_out_RD[WIDTH-1]}}, trem_out_RD}};
                state_1 <= IDLE;
              end else begin
                fifo2_d_in <= {{{PADDING{trem_in_LD[WIDTH-1]}}, trem_in_LD},{{PADDING{trem_in_RD[WIDTH-1]}}, trem_in_RD}};
                state_1 <= IDLE;
              end
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

amplifier u_amplifier(
    .data_valid(amp_in_valid),
    .data_ready(amp_out_valid),
    .sck(top_dsp_clk),
    .reset(top_dsp_reset),
    .in_LD(amp_in_LD),
    .in_RD(amp_in_RD),
    .G(gain_value),
    .out_LD(amp_out_LD),
    .out_RD(amp_out_RD)
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

tremolo_lfo LFO(
    .data_valid(trem_in_valid),
    .sck(top_dsp_clk),
    .reset(top_dsp_reset),
    .control_rate(control_rate_active),
    .control_depth(control_depth_active), 
    .in_LD(trem_in_LD), 
    .in_RD(trem_in_RD),
    .data_ready(lfo_out_valid),  
    .out_LD(lfo_out_LD),
    .out_RD(lfo_out_RD),   
    .tremolo_gain(trem_gain)
);

amplifier trem_amplifier(
    .data_valid(lfo_out_valid),
    .sck(top_dsp_clk),
    .reset(top_dsp_reset),
    .in_LD(lfo_out_LD),
    .in_RD(lfo_out_RD),
    .G(trem_gain),
    .data_ready(trem_out_valid),
    .out_LD(trem_out_LD),
    .out_RD(trem_out_RD)
);

async_fifo #(
    .WIDTH(FIFO_WIDTH)
) u_fifo2(
    .rd_clk(top_i2s_clk),
    .rd_reset(top_i2s_reset),
    .rd_en(fifo2_rd_en),
    .wr_clk(top_dsp_clk),
    .wr_reset(top_dsp_reset),
    .wr_en(trem_out_valid),
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