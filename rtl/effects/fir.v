/* ==============================================================================
 * Module:      FIR
 * Description: Time-multiplexed 63-tap stereo FIR low-pass filter using
 * separate circular sample buffers and one shared MAC datapath.
 *
 * On `data_valid`, one signed 24-bit left/right audio frame is stored in the
 * circular buffers. The module then processes all 63 taps for the left channel,
 * followed by all 63 taps for the right channel.
 *
 * Arithmetic Format:
 * - Audio samples: signed 24-bit
 * - Coefficients: signed 16-bit Q1.15, loaded from a memory file
 * - Accumulator: signed 48-bit
 * - Final result: rounded, shifted right by 15, and saturated to 24 bits
 *
 * Processing States:
 * - CLEAR: Initializes both circular buffers to zero after reset
 * - IDLE/STORE: Captures and stores a new stereo frame
 * - MAC: Performs one multiply-accumulate operation per clock
 * - ROUND/SCALE/SAT: Converts the accumulated result back to 24-bit audio
 * - DONE: Stores each channel result and pulses `data_ready` when both outputs
 *   are valid
 *
 * Left and right channels have independent sample histories but share the
 * coefficient ROM, multiplier, accumulator, and output-processing logic.
 * ==============================================================================
 */


module fir
#(
    parameter WIDTH = 24,
    parameter COEFFICIENT_WIDTH = 16,
    parameter FRAC_BITS = 15,
    parameter NUM_TAPS = 63
)
(
    input wire                             clk,
    input wire                           reset,
    input wire                      data_valid,
    input wire signed [WIDTH-1:0]        in_LD,
    input wire signed [WIDTH-1:0]        in_RD,

    output wire signed [WIDTH-1:0]      out_LD,
    output wire signed [WIDTH-1:0]      out_RD,
    output wire                      data_ready
);

// Constant parameter for saturation check
localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

wire signed [32:0] max_ext;
wire signed [32:0] min_ext;

assign max_ext = {{(9){MAX[WIDTH-1]}}, MAX};
assign min_ext = {{(9){MIN[WIDTH-1]}}, MIN};

// State machine
localparam IDLE  =  3'd0;
localparam STORE =  3'd1;
localparam MAC   =  3'd2;
localparam ROUND =  3'd3;
localparam SCALE =  3'd4;
localparam SAT   =  3'd5;
localparam DONE  =  3'd6;
localparam CLEAR =  3'd7;

localparam LEFT  = 1'b0;
localparam RIGHT  = 1'b1;

reg [2:0] state;
reg channel;

// RAM clear
reg [5:0] clear_address;

//Coefficient ROM
reg signed [COEFFICIENT_WIDTH-1:0] coeff_rom [0:NUM_TAPS-1];
reg [5:0] tap_index;

initial begin
    $readmemh("fir_8khz_63tap_q15.mem", coeff_rom);
end

//Circular RAM for samples
reg signed [WIDTH-1:0] l_cir_ram [0:NUM_TAPS-1];
reg signed [WIDTH-1:0] r_cir_ram [0:NUM_TAPS-1];
reg [5:0] rd_pointer;
reg [5:0] wr_pointer;


//Calculation
reg signed [47:0] accumulator;
reg signed [47:0] rounded_acc;
reg signed [32:0] scaled_acc;
reg signed [WIDTH-1:0] processed_acc;
reg signed [WIDTH-1:0] reg_in_LD;
reg signed [WIDTH-1:0] reg_in_RD;
reg signed [WIDTH-1:0] saved_result;
reg signed [WIDTH-1:0] reg_out_LD;
reg signed [WIDTH-1:0] reg_out_RD;

assign out_LD = reg_out_LD;
assign out_RD = reg_out_RD;

reg reg_data_ready;
assign data_ready = reg_data_ready;

always @(posedge clk) begin
    if (reset) begin
        accumulator <= 0;
        rounded_acc <= 0;
        scaled_acc <= 0;
        processed_acc <= 0;
        reg_in_LD <= 0;
        reg_in_RD <= 0;
        saved_result <= 0;
        reg_out_LD <= 0;
        reg_out_RD <= 0;
        rd_pointer <= 0;
        wr_pointer <= 0;
        tap_index <= 0;
        reg_data_ready <= 0;
        state <= CLEAR;
        clear_address <= 0;
        channel <= LEFT;
    end 
    else begin
      reg_data_ready <= 0;
        
      case (state)
        IDLE: begin
          if (data_valid) begin
            reg_in_LD <= in_LD;
            reg_in_RD <= in_RD;
            state <= STORE;
          end
        end
        
        STORE: begin
          l_cir_ram[wr_pointer] <= reg_in_LD;
          r_cir_ram[wr_pointer] <= reg_in_RD;

          wr_pointer <= (wr_pointer == NUM_TAPS-1) ? 0 : wr_pointer + 1;
          rd_pointer <= wr_pointer;
          tap_index <= 0;
          accumulator <= 0;
          channel <= LEFT;
          
          state <= MAC;
        end

        MAC: begin
          if (channel == LEFT) begin 
            accumulator <= accumulator + l_cir_ram[rd_pointer] * coeff_rom[tap_index];
            rd_pointer <= (rd_pointer == 0) ? (NUM_TAPS-1) : rd_pointer - 1;
          end else if (channel == RIGHT) begin
            accumulator <= accumulator + r_cir_ram[rd_pointer] * coeff_rom[tap_index];
            rd_pointer <= (rd_pointer == 0) ? (NUM_TAPS-1) : rd_pointer - 1;
          end
 
          tap_index <= tap_index + 1;
          if (tap_index == (NUM_TAPS-1)) begin
            state <= ROUND;
          end
        end
        
        ROUND: begin

          if (accumulator >= 0) begin
            rounded_acc <= accumulator + 48'sd16384;
          end else if (accumulator < 0) begin
            rounded_acc <= accumulator + 48'sd16384;
          end

          state <= SCALE;
        end

        SCALE: begin

          scaled_acc <= rounded_acc[47:15];
          state <= SAT;
        end
        
        SAT: begin
          if (scaled_acc > max_ext) begin 
            processed_acc <= MAX;  
          end else if (scaled_acc < min_ext) begin
            processed_acc <= MIN;  
          end else begin
            processed_acc <= scaled_acc[WIDTH-1:0];     
          end

          state <= DONE;
        end

        DONE: begin
          if (channel == LEFT) begin
            saved_result <= processed_acc;
            channel <= RIGHT;
            rd_pointer <= (wr_pointer == 0) ? (NUM_TAPS-1) : wr_pointer - 1'b1;           
            tap_index <= 0;
            accumulator <= 0;
            state <= MAC;
          end else if (channel == RIGHT) begin
            reg_out_LD <= saved_result;
            reg_out_RD <= processed_acc;
            reg_data_ready <= 1;
            state <= IDLE;
          end
        end

        CLEAR: begin
          l_cir_ram[clear_address] <= 0;
          r_cir_ram[clear_address] <= 0;

          if (clear_address == NUM_TAPS-1) begin
            clear_address <= 0;
            state <= IDLE;
          end else begin
            clear_address <= clear_address + 1;
          end
        end

        default: begin
          state <= IDLE;
        end
      endcase
    end
end
endmodule


