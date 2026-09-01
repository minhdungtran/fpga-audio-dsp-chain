/* ==============================================================================
 * Module:      Amplifier
 * Description: Fixed-point stereo audio amplifier for signed PCM samples.
 *
 *              This module receives one complete stereo audio frame containing
 *              signed left and right PCM samples. When `data_valid` is asserted,
 *              the input samples `in_LD` and `in_RD` are captured and multiplied
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
 *              - `out_LD` and `out_RD` contain the amplified left and right
 *                samples.
 *              - `data_ready` pulses high for one `sck` cycle when `out_LD`
 *                and `out_RD` contain a valid amplified stereo frame.
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
    input wire                      data_valid,       // Pulse high when the data of RV is ready
    input wire                             sck,        
    input wire                           reset,
    input wire signed  [GAIN_LENGTH-1:0]     G,      // The amplifier constant represent in 8 bits
    input wire signed  [WIDTH-1:0]       in_LD,      // Left channel data flow in 
    input wire signed  [WIDTH-1:0]       in_RD,      // Right channel data flow in 

    output wire                     data_ready,      // Pulse high when amplifier is ready
    output wire signed [WIDTH-1:0]      out_LD,      // Left channel after amplified
    output wire signed [WIDTH-1:0]      out_RD      // Right channel after amplified
);

localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

wire signed [WIDTH+GAIN_LENGTH-1:0] max_ext;
wire signed [WIDTH+GAIN_LENGTH-1:0] min_ext;

assign max_ext = {{(GAIN_LENGTH){MAX[WIDTH-1]}}, MAX};
assign min_ext = {{(GAIN_LENGTH){MIN[WIDTH-1]}}, MIN};

reg signed [GAIN_LENGTH-1:0] reg_gain;

reg signed [WIDTH + GAIN_LENGTH-1 :0] multi_LD;
reg signed [WIDTH + GAIN_LENGTH-1 :0] multi_RD;

reg signed [WIDTH + GAIN_LENGTH-1 :0] amp_LD;
reg signed [WIDTH + GAIN_LENGTH-1 :0] amp_RD;

reg signed [WIDTH-1:0] reg_in_LD;
reg signed [WIDTH-1:0] reg_in_RD;

reg signed [WIDTH-1:0] reg_out_LD;
reg signed [WIDTH-1:0] reg_out_RD;

reg reg_data_ready;
reg sat_check;
reg multiplication;
reg shifting;


assign data_ready = reg_data_ready;
assign out_LD = reg_out_LD;
assign out_RD = reg_out_RD;


always @(posedge sck) begin 

  if (reset) begin
    reg_in_LD <= 0;
    reg_in_RD <= 0;
    reg_out_LD <= 0;
    reg_out_RD <= 0;
    multi_LD <= 0;
    multi_RD <= 0;
    amp_LD <= 0;
    amp_RD <= 0;
    reg_gain <= 0;
    reg_data_ready <= 0;
    sat_check <= 0;
    multiplication <= 0;
    shifting <= 0;
  end else begin

    multiplication <= data_valid;
    shifting <= multiplication;
    sat_check <= shifting;
    reg_data_ready <= sat_check;


    if (data_valid) begin
      reg_in_LD <= in_LD ;
      reg_in_RD <= in_RD;
      reg_gain <= G;

    end if (multiplication) begin
      multi_LD <= $signed(reg_in_LD) * $signed(reg_gain);
      multi_RD <= $signed(reg_in_RD) * $signed(reg_gain);

    end if (shifting) begin
      amp_LD <= $signed(multi_LD) >>> 14;
      amp_RD <= $signed(multi_RD) >>> 14;

    end if (sat_check) begin
    //check if the left channel reach saturation
      if ($signed(amp_LD) > $signed(max_ext)) begin 
          reg_out_LD <= MAX;
      end 
      else if ($signed(amp_LD) < $signed(min_ext)) begin 
          reg_out_LD <= MIN;
      end 
      else begin
          reg_out_LD <= amp_LD[WIDTH-1:0];
      end

    //check if the right channel reach saturation
      if ($signed(amp_RD) > $signed(max_ext)) begin 
          reg_out_RD <= MAX;
      end 
      else if ($signed(amp_RD) < $signed(min_ext)) begin 
          reg_out_RD <= MIN;
      end 
      else begin
          reg_out_RD <= amp_RD[WIDTH-1:0];
      end
    end 
  end 
end
endmodule





