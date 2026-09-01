/* ==============================================================================
 * Module:      tremolo_lfo
 * Description: Fixed-point Low-Frequency Oscillator (LFO) for stereo tremolo 
 * effects.
 *
 * This module generates a time-varying, unipolar sine wave to
 * modulate audio amplitude. When `data_valid` is high,
 * it sequences through a multi-cycle pipeline to calculate an
 * instantaneous gain multiplier intended for a downstream
 * amplifier block, while passing the audio samples through a
 * delay path to maintain synchronization.
 *
 * LFO and Modulation Format:
 * - The LFO uses a 16-bit phase accumulator. `control_rate` is
 * added to the accumulator per valid audio frame to dictate
 * oscillation frequency.
 * - The upper 8 bits of the accumulator index a 256-word ROM
 * containing a unipolar sine wave scaled to unsigned U0.14 format.
 * - `control_depth` dictates effect intensity, strictly formatted 
 * as an unsigned U0.14 fraction.
 *
 * Processing Pipeline:
 * - Cycle 0 (data_valid): Captures `in_LD`/`in_RD` into registers 
 * and steps the 16-bit LFO phase accumulator.
 * - Cycle 1 (multi_D): Multiplies the U0.14 LFO ROM data by the 
 * U0.14 `control_depth`.
 * - Cycle 2 (shift_D): Arithmetically truncates the 28-bit product 
 * back to 14 fractional bits (U0.14 alignment).
 * - Cycle 3 (subtract): Subtracts the depth-scaled LFO value from 
 * a digital 1.0 (to create the `tremolo_gain` instantaneous gain).
 *
 * Output behavior:
 * - `out_LD` and `out_RD` output the unmodified original audio
 * samples, safely delayed to match the 4-cycle math pipeline.
 * - `data_ready` pulses high for one `sck` cycle to signal that 
 * the synchronized audio and calculated tremolo gain are ready 
 * for the multiplier stage.
 * ==============================================================================
 */


module tremolo_lfo
#(
    parameter WIDTH = 24
)
(
    input wire                      data_valid,       // Pulse high when the data of RV is ready
    input wire                             sck,        
    input wire                           reset,
    input wire         [15:0]     control_rate,    
    input wire         [13:0]    control_depth,      
    input wire signed  [WIDTH-1:0]       in_LD,      // Left channel data flow in from Receiver
    input wire signed  [WIDTH-1:0]       in_RD,      // Right channel data flow in from Receiver

    output wire                     data_ready,      // Pulse high when amplifier is ready
    output wire signed [WIDTH-1:0]      out_LD,      // Left channel after amplified
    output wire signed [WIDTH-1:0]      out_RD,      // Right channel after amplified
    output wire signed [15:0]      tremolo_gain

);

reg [7:0] rom_address; //to access the LUT 
reg [13:0] rom_data;

reg [15:0] accumulator;

reg [WIDTH-1:0] reg_LD;
reg [WIDTH-1:0] reg_RD;
reg [WIDTH-1:0] reg_out_LD;
reg [WIDTH-1:0] reg_out_RD;

reg [27:0] multiplication;
reg [15:0] shifted;
reg [15:0] reg_tremolo_gain;

reg multi_D;
reg shift_D;
reg subtract;
reg reg_data_ready;

assign data_ready = reg_data_ready;
assign out_LD = reg_out_LD;
assign out_RD = reg_out_RD;
assign tremolo_gain = reg_tremolo_gain;

always @(posedge sck) begin
    if (reset) begin
        rom_address <= 0;
        accumulator <= 0;
        reg_LD <= 0;
        reg_RD <= 0;
        reg_out_LD <= 0;
        reg_out_RD <= 0;
        multiplication <= 0;
        shifted <= 0;
        reg_tremolo_gain <= 0;
        reg_data_ready <= 0;
        multi_D <= 0;
        shift_D <= 0;
        subtract <= 0;
    end else begin
        multi_D <= data_valid;
        shift_D <= multi_D;
        subtract <= shift_D;
        reg_data_ready <= subtract;

        if (data_valid) begin
          reg_LD <= in_LD;
          reg_RD <= in_RD;
          accumulator <= accumulator + control_rate;
          rom_address <= accumulator[15:8];

        end if (multi_D) begin
            multiplication <= control_depth * rom_data;

        end if (shift_D) begin
            shifted <= {2'b00,multiplication[27:14]};
        
        end if (subtract) begin
            reg_tremolo_gain <= (1<<14) - shifted;
            reg_out_LD <= reg_LD;
            reg_out_RD <= reg_RD;
        end 

    end
end

always @(*) begin
    case(rom_address)
      8'h01: rom_data = 14'h20C9;
      8'h02: rom_data = 14'h2192;
      8'h03: rom_data = 14'h225B;
      8'h04: rom_data = 14'h2323;
      8'h05: rom_data = 14'h23EB;
      8'h06: rom_data = 14'h24B2;
      8'h07: rom_data = 14'h2579;
      8'h08: rom_data = 14'h263E;
      8'h09: rom_data = 14'h2703;
      8'h0A: rom_data = 14'h27C6;
      8'h0B: rom_data = 14'h2889;
      8'h0C: rom_data = 14'h294A;
      8'h0D: rom_data = 14'h2A0A;
      8'h0E: rom_data = 14'h2AC8;
      8'h0F: rom_data = 14'h2B84;
      8'h10: rom_data = 14'h2C3F;
      8'h11: rom_data = 14'h2CF8;
      8'h12: rom_data = 14'h2DAF;
      8'h13: rom_data = 14'h2E63;
      8'h14: rom_data = 14'h2F16;
      8'h15: rom_data = 14'h2FC6;
      8'h16: rom_data = 14'h3074;
      8'h17: rom_data = 14'h311F;
      8'h18: rom_data = 14'h31C7;
      8'h19: rom_data = 14'h326D;
      8'h1A: rom_data = 14'h3310;
      8'h1B: rom_data = 14'h33B0;
      8'h1C: rom_data = 14'h344D;
      8'h1D: rom_data = 14'h34E7;
      8'h1E: rom_data = 14'h357D;
      8'h1F: rom_data = 14'h3611;
      8'h20: rom_data = 14'h36A1;
      8'h21: rom_data = 14'h372D;
      8'h22: rom_data = 14'h37B6;
      8'h23: rom_data = 14'h383B;
      8'h24: rom_data = 14'h38BD;
      8'h25: rom_data = 14'h393A;
      8'h26: rom_data = 14'h39B4;
      8'h27: rom_data = 14'h3A2A;
      8'h28: rom_data = 14'h3A9B;
      8'h29: rom_data = 14'h3B09;
      8'h2A: rom_data = 14'h3B73;
      8'h2B: rom_data = 14'h3BD8;
      8'h2C: rom_data = 14'h3C39;
      8'h2D: rom_data = 14'h3C95;
      8'h2E: rom_data = 14'h3CED;
      8'h2F: rom_data = 14'h3D41;
      8'h30: rom_data = 14'h3D90;
      8'h31: rom_data = 14'h3DDB;
      8'h32: rom_data = 14'h3E21;
      8'h33: rom_data = 14'h3E63;
      8'h34: rom_data = 14'h3E9F;
      8'h35: rom_data = 14'h3ED7;
      8'h36: rom_data = 14'h3F0A;
      8'h37: rom_data = 14'h3F39;
      8'h38: rom_data = 14'h3F63;
      8'h39: rom_data = 14'h3F87;
      8'h3A: rom_data = 14'h3FA7;
      8'h3B: rom_data = 14'h3FC2;
      8'h3C: rom_data = 14'h3FD9;
      8'h3D: rom_data = 14'h3FEA;
      8'h3E: rom_data = 14'h3FF6;
      8'h3F: rom_data = 14'h3FFE;
      8'h40: rom_data = 14'h3FFF;
      8'h41: rom_data = 14'h3FFE;
      8'h42: rom_data = 14'h3FF6;
      8'h43: rom_data = 14'h3FEA;
      8'h44: rom_data = 14'h3FD9;
      8'h45: rom_data = 14'h3FC2;
      8'h46: rom_data = 14'h3FA7;
      8'h47: rom_data = 14'h3F87;
      8'h48: rom_data = 14'h3F63;
      8'h49: rom_data = 14'h3F39;
      8'h4A: rom_data = 14'h3F0A;
      8'h4B: rom_data = 14'h3ED7;
      8'h4C: rom_data = 14'h3E9F;
      8'h4D: rom_data = 14'h3E63;
      8'h4E: rom_data = 14'h3E21;
      8'h4F: rom_data = 14'h3DDB;
      8'h50: rom_data = 14'h3D90;
      8'h51: rom_data = 14'h3D41;
      8'h52: rom_data = 14'h3CED;
      8'h53: rom_data = 14'h3C95;
      8'h54: rom_data = 14'h3C39;
      8'h55: rom_data = 14'h3BD8;
      8'h56: rom_data = 14'h3B73;
      8'h57: rom_data = 14'h3B09;
      8'h58: rom_data = 14'h3A9B;
      8'h59: rom_data = 14'h3A2A;
      8'h5A: rom_data = 14'h39B4;
      8'h5B: rom_data = 14'h393A;
      8'h5C: rom_data = 14'h38BD;
      8'h5D: rom_data = 14'h383B;
      8'h5E: rom_data = 14'h37B6;
      8'h5F: rom_data = 14'h372D;
      8'h60: rom_data = 14'h36A1;
      8'h61: rom_data = 14'h3611;
      8'h62: rom_data = 14'h357D;
      8'h63: rom_data = 14'h34E7;
      8'h64: rom_data = 14'h344D;
      8'h65: rom_data = 14'h33B0;
      8'h66: rom_data = 14'h3310;
      8'h67: rom_data = 14'h326D;
      8'h68: rom_data = 14'h31C7;
      8'h69: rom_data = 14'h311F;
      8'h6A: rom_data = 14'h3074;
      8'h6B: rom_data = 14'h2FC6;
      8'h6C: rom_data = 14'h2F16;
      8'h6D: rom_data = 14'h2E63;
      8'h6E: rom_data = 14'h2DAF;
      8'h6F: rom_data = 14'h2CF8;
      8'h70: rom_data = 14'h2C3F;
      8'h71: rom_data = 14'h2B84;
      8'h72: rom_data = 14'h2AC8;
      8'h73: rom_data = 14'h2A0A;
      8'h74: rom_data = 14'h294A;
      8'h75: rom_data = 14'h2889;
      8'h76: rom_data = 14'h27C6;
      8'h77: rom_data = 14'h2703;
      8'h78: rom_data = 14'h263E;
      8'h79: rom_data = 14'h2579;
      8'h7A: rom_data = 14'h24B2;
      8'h7B: rom_data = 14'h23EB;
      8'h7C: rom_data = 14'h2323;
      8'h7D: rom_data = 14'h225B;
      8'h7E: rom_data = 14'h2192;
      8'h7F: rom_data = 14'h20C9;
      8'h80: rom_data = 14'h2000;
      8'h81: rom_data = 14'h1F37;
      8'h82: rom_data = 14'h1E6E;
      8'h83: rom_data = 14'h1DA5;
      8'h84: rom_data = 14'h1CDD;
      8'h85: rom_data = 14'h1C15;
      8'h86: rom_data = 14'h1B4E;
      8'h87: rom_data = 14'h1A87;
      8'h88: rom_data = 14'h19C2;
      8'h89: rom_data = 14'h18FD;
      8'h8A: rom_data = 14'h183A;
      8'h8B: rom_data = 14'h1777;
      8'h8C: rom_data = 14'h16B6;
      8'h8D: rom_data = 14'h15F6;
      8'h8E: rom_data = 14'h1538;
      8'h8F: rom_data = 14'h147C;
      8'h90: rom_data = 14'h13C1;
      8'h91: rom_data = 14'h1308;
      8'h92: rom_data = 14'h1251;
      8'h93: rom_data = 14'h119D;
      8'h94: rom_data = 14'h10EA;
      8'h95: rom_data = 14'h103A;
      8'h96: rom_data = 14'h0F8C;
      8'h97: rom_data = 14'h0EE1;
      8'h98: rom_data = 14'h0E39;
      8'h99: rom_data = 14'h0D93;
      8'h9A: rom_data = 14'h0CF0;
      8'h9B: rom_data = 14'h0C50;
      8'h9C: rom_data = 14'h0BB3;
      8'h9D: rom_data = 14'h0B19;
      8'h9E: rom_data = 14'h0A83;
      8'h9F: rom_data = 14'h09EF;
      8'hA0: rom_data = 14'h095F;
      8'hA1: rom_data = 14'h08D3;
      8'hA2: rom_data = 14'h084A;
      8'hA3: rom_data = 14'h07C5;
      8'hA4: rom_data = 14'h0743;
      8'hA5: rom_data = 14'h06C6;
      8'hA6: rom_data = 14'h064C;
      8'hA7: rom_data = 14'h05D6;
      8'hA8: rom_data = 14'h0565;
      8'hA9: rom_data = 14'h04F7;
      8'hAA: rom_data = 14'h048D;
      8'hAB: rom_data = 14'h0428;
      8'hAC: rom_data = 14'h03C7;
      8'hAD: rom_data = 14'h036B;
      8'hAE: rom_data = 14'h0313;
      8'hAF: rom_data = 14'h02BF;
      8'hB0: rom_data = 14'h0270;
      8'hB1: rom_data = 14'h0225;
      8'hB2: rom_data = 14'h01DF;
      8'hB3: rom_data = 14'h019D;
      8'hB4: rom_data = 14'h0161;
      8'hB5: rom_data = 14'h0129;
      8'hB6: rom_data = 14'h00F6;
      8'hB7: rom_data = 14'h00C7;
      8'hB8: rom_data = 14'h009D;
      8'hB9: rom_data = 14'h0079;
      8'hBA: rom_data = 14'h0059;
      8'hBB: rom_data = 14'h003E;
      8'hBC: rom_data = 14'h0027;
      8'hBD: rom_data = 14'h0016;
      8'hBE: rom_data = 14'h000A;
      8'hBF: rom_data = 14'h0002;
      8'hC0: rom_data = 14'h0000;
      8'hC1: rom_data = 14'h0002;
      8'hC2: rom_data = 14'h000A;
      8'hC3: rom_data = 14'h0016;
      8'hC4: rom_data = 14'h0027;
      8'hC5: rom_data = 14'h003E;
      8'hC6: rom_data = 14'h0059;
      8'hC7: rom_data = 14'h0079;
      8'hC8: rom_data = 14'h009D;
      8'hC9: rom_data = 14'h00C7;
      8'hCA: rom_data = 14'h00F6;
      8'hCB: rom_data = 14'h0129;
      8'hCC: rom_data = 14'h0161;
      8'hCD: rom_data = 14'h019D;
      8'hCE: rom_data = 14'h01DF;
      8'hCF: rom_data = 14'h0225;
      8'hD0: rom_data = 14'h0270;
      8'hD1: rom_data = 14'h02BF;
      8'hD2: rom_data = 14'h0313;
      8'hD3: rom_data = 14'h036B;
      8'hD4: rom_data = 14'h03C7;
      8'hD5: rom_data = 14'h0428;
      8'hD6: rom_data = 14'h048D;
      8'hD7: rom_data = 14'h04F7;
      8'hD8: rom_data = 14'h0565;
      8'hD9: rom_data = 14'h05D6;
      8'hDA: rom_data = 14'h064C;
      8'hDB: rom_data = 14'h06C6;
      8'hDC: rom_data = 14'h0743;
      8'hDD: rom_data = 14'h07C5;
      8'hDE: rom_data = 14'h084A;
      8'hDF: rom_data = 14'h08D3;
      8'hE0: rom_data = 14'h095F;
      8'hE1: rom_data = 14'h09EF;
      8'hE2: rom_data = 14'h0A83;
      8'hE3: rom_data = 14'h0B19;
      8'hE4: rom_data = 14'h0BB3;
      8'hE5: rom_data = 14'h0C50;
      8'hE6: rom_data = 14'h0CF0;
      8'hE7: rom_data = 14'h0D93;
      8'hE8: rom_data = 14'h0E39;
      8'hE9: rom_data = 14'h0EE1;
      8'hEA: rom_data = 14'h0F8C;
      8'hEB: rom_data = 14'h103A;
      8'hEC: rom_data = 14'h10EA;
      8'hED: rom_data = 14'h119D;
      8'hEE: rom_data = 14'h1251;
      8'hEF: rom_data = 14'h1308;
      8'hF0: rom_data = 14'h13C1;
      8'hF1: rom_data = 14'h147C;
      8'hF2: rom_data = 14'h1538;
      8'hF3: rom_data = 14'h15F6;
      8'hF4: rom_data = 14'h16B6;
      8'hF5: rom_data = 14'h1777;
      8'hF6: rom_data = 14'h183A;
      8'hF7: rom_data = 14'h18FD;
      8'hF8: rom_data = 14'h19C2;
      8'hF9: rom_data = 14'h1A87;
      8'hFA: rom_data = 14'h1B4E;
      8'hFB: rom_data = 14'h1C15;
      8'hFC: rom_data = 14'h1CDD;
      8'hFD: rom_data = 14'h1DA5;
      8'hFE: rom_data = 14'h1E6E;
      8'hFF: rom_data = 14'h1F37;
      default: rom_data = 14'h2000;
    endcase
end
endmodule


