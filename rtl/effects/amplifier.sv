/* ==============================================================================
 * Module:      Amplifier
 * Description: Fixed-point stereo audio amplifier for signed PCM samples.
 *
 *              This module receives one complete stereo audio frame containing
 *              signed left and right PCM samples. When `valid_i` is asserted,
 *              the input samples `ld_I` and `rd_I` are captured and multiplied
 *              by the signed fixed-point gain value `G`.
 *
 *              Gain format:
 *              - `G` uses signed Q2.14 fixed-point format.
 *              - The real gain value is calculated as:
 *                    gain_real = G / 2^14

 *              Processing behavior:
 *              - Input samples are treated as signed two's-complement values.
 *              - Each channel is multiplied by the signed gain value.
 *              - The multiplication result is arithmetically shifted right by
 *                14 bits to convert the Q2.14 result back to normal PCM scale.
 *              - Saturation logic clips the shifted result to the valid signed
 *                `WIDTH`-bit audio range before driving the outputs.
 *
 *              Output behavior:
 *              - `ld_O` and `rd_O` contain the amplified left and right
 *                samples.
 *              - `valid_o` pulses high for one `sck` cycle when `ld_O`
 *                and `rd_O` contain a valid amplified stereo frame.
 *              - Output samples remain stable until the next processed frame is
 *                completed.
 *
 *              Notes:
 *              - For normal volume control, use non-negative gain values.
 *              - Negative gain values are valid, but they invert the audio
 *                waveform polarity.
 *              - Saturation is checked after the fixed-point right shift, not
 *                directly after multiplication.
 * ==============================================================================
 */

module amplifier
#(
    parameter WIDTH = 24,
    parameter GAIN_LENGTH = 16
)
(
    input logic                             valid_i,       // Pulse high when previous modules have available samples
    input logic                             ready_i,       // Pulse high when the next module can receive samples
    input logic                             dsp_clk,        
    input logic                               reset,
    input logic                              bypass,
    input logic         [GAIN_LENGTH-1:0]         g,      // The amplifier constant represent in 8 bits
    input logic signed  [WIDTH-1:0]            ld_i,      // Left channel data flow in 
    input logic signed  [WIDTH-1:0]            rd_i,      // Right channel data flow in 
    
    output logic                            valid_o,      // Pulse high when this module's samples can be sent to next module
    output logic                            ready_o,      // Pulse high this module can accept new samples from previous modules
    output logic signed [WIDTH-1:0]            ld_o,      // Left channel output 
    output logic signed [WIDTH-1:0]            rd_o       // Right channel output
);

localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

typedef enum logic [1:0] {
  LOAD, MULTIPLICATION, SAT, DONE
} state_t;

state_t state;

logic signed [WIDTH+GAIN_LENGTH-1:0] max_ext;
logic signed [WIDTH+GAIN_LENGTH-1:0] min_ext;

assign max_ext = {{(GAIN_LENGTH){MAX[WIDTH-1]}}, MAX};
assign min_ext = {{(GAIN_LENGTH){MIN[WIDTH-1]}}, MIN};

logic signed [GAIN_LENGTH-1:0] reg_gain;
logic bypass_r;

logic signed [WIDTH + GAIN_LENGTH-1 :0] ld_product;
logic signed [WIDTH + GAIN_LENGTH-1 :0] rd_product;

logic signed [WIDTH-1:0] ld_i_r;
logic signed [WIDTH-1:0] rd_i_r;

logic signed [WIDTH-1:0] ld_o_r;
logic signed [WIDTH-1:0] rd_o_r;

assign valid_o = (state == DONE);
assign ready_o = (state == LOAD) && !reset;

assign ld_o = ld_o_r;
assign rd_o = rd_o_r;

always_ff @(posedge dsp_clk) begin 
  if (reset) begin
    ld_i_r <= 0;
    rd_i_r <= 0;
    ld_o_r <= 0;
    rd_o_r <= 0;
    ld_product <= 0;
    rd_product <= 0;
    reg_gain <= $signed(g);;
    bypass_r <= bypass;
    state <= LOAD;

  end else begin
    case (state)
      LOAD: begin
        if (valid_i && ready_o) begin
          if (bypass_r) begin
            ld_o_r <= ld_i;
            rd_o_r <= rd_i;
            state <= DONE;
          end
          else begin
            ld_i_r <= ld_i;
            rd_i_r <= rd_i;
            state <= MULTIPLICATION;
          end
        end
      end

      MULTIPLICATION: begin
        ld_product <= ($signed(ld_i_r) * $signed(reg_gain)) >>> 14;
        rd_product <= ($signed(rd_i_r) * $signed(reg_gain)) >>> 14;
        state <= SAT;
      end

      SAT: begin
        if ($signed(ld_product) > $signed(max_ext)) begin 
            ld_o_r <= MAX;
        end 
        else if ($signed(ld_product) < $signed(min_ext)) begin 
            ld_o_r <= MIN;
        end 
        else begin
            ld_o_r <= ld_product[WIDTH-1:0];
        end

        if ($signed(rd_product) > $signed(max_ext)) begin 
            rd_o_r <= MAX;
        end 
        else if ($signed(rd_product) < $signed(min_ext)) begin 
            rd_o_r <= MIN;
        end 
        else begin
            rd_o_r <= rd_product[WIDTH-1:0];
        end

        state <= DONE;
      end 

      DONE: begin
        if (ready_i) begin
          state <= LOAD;
        end
      end

      default: begin
        state <= LOAD;
      end
      
    endcase
  end
end 
endmodule





