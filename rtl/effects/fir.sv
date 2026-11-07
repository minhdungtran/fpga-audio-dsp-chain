module fir
#(
    parameter WIDTH = 24,
    parameter COEFF_WIDTH = 16,
    parameter FRAC_BITS = 15,
    parameter NUM_TAPS = 63
)
(
    input logic                         dsp_clk,
    input logic                           reset,
    input logic                         valid_i,
    input logic                         ready_i,
    input logic                          bypass,
    input logic [1:0]                    mode_i,
    input logic signed [WIDTH-1:0]         ld_i,
    input logic signed [WIDTH-1:0]         rd_i,

    output logic                         valid_o,
    output logic                         ready_o,
    output logic signed [WIDTH-1:0]         ld_o,
    output logic signed [WIDTH-1:0]         rd_o
);

// Constant parameter for saturation check
localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

localparam int PRODUCT_WIDTH = WIDTH + COEFF_WIDTH;
localparam int ACC_WIDTH = PRODUCT_WIDTH + $clog2(NUM_TAPS);

localparam logic signed [ACC_WIDTH-1:0] ROUND_OFFSET =
    ACC_WIDTH'(1) <<< (FRAC_BITS - 1);

wire signed [ACC_WIDTH-1:0] max_ext;
wire signed [ACC_WIDTH-1:0] min_ext;

assign max_ext = {{(ACC_WIDTH-WIDTH){MAX[WIDTH-1]}}, MAX};
assign min_ext = {{(ACC_WIDTH-WIDTH){MIN[WIDTH-1]}}, MIN};

typedef enum logic[3:0] { 
  LOAD, WRITE, MAC, ROUND, SAT, STORE, DONE, CLEAR
} state_t;

typedef enum  logic {
  LEFT, RIGHT
} channel_t;

typedef enum logic[1:0] {
  BRIGHT, WARM, DARK
} mode_t;

state_t state;
channel_t channel;

// Configuration
mode_t mode_r;
logic bypass_r;

// RAM clear
logic [5:0] clear_address;

//Coefficient ROM
logic signed [COEFF_WIDTH-1:0] coeff_bright [0:NUM_TAPS-1];
logic signed [COEFF_WIDTH-1:0] coeff_warm   [0:NUM_TAPS-1];
logic signed [COEFF_WIDTH-1:0] coeff_dark   [0:NUM_TAPS-1];

logic signed [COEFF_WIDTH-1:0] selected_coeff;
logic [5:0] tap_index;

initial begin
    $readmemh("coefficients/fir/mem/fir_bright_q15.mem", coeff_bright);
    $readmemh("coefficients/fir/mem/fir_warm_q15.mem",   coeff_warm);
    $readmemh("coefficients/fir/mem/fir_dark_q15.mem",   coeff_dark);
end

//Circular RAM for samples
logic signed [WIDTH-1:0] l_cir_ram [0:NUM_TAPS-1];
logic signed [WIDTH-1:0] r_cir_ram [0:NUM_TAPS-1];
logic [5:0] rd_pointer;
logic [5:0] wr_pointer;


//Calculation
logic signed [ACC_WIDTH-1:0] accumulator;
logic signed [ACC_WIDTH-1:0] rounded_acc;
logic signed [WIDTH-1:0] processed_acc;
logic signed [WIDTH-1:0] ld_i_r;
logic signed [WIDTH-1:0] rd_i_r;
logic signed [WIDTH-1:0] saved_result;
logic signed [WIDTH-1:0] ld_o_r;
logic signed [WIDTH-1:0] rd_o_r;

assign ld_o = ld_o_r;
assign rd_o = rd_o_r;

// Handshake 
assign valid_o = (state == DONE);
assign ready_o = (state == LOAD) && !reset;

always_comb begin
    case (mode_r)
        BRIGHT:   selected_coeff = coeff_bright[tap_index];
        WARM:     selected_coeff = coeff_warm[tap_index];
        DARK:     selected_coeff = coeff_dark[tap_index];
        default:  selected_coeff = coeff_warm[tap_index];
    endcase
end

always @(posedge dsp_clk) begin
    if (reset) begin
      bypass_r <= bypass;
      mode_r <= mode_t'(mode_i);
      accumulator <= 0;
      rounded_acc <= 0;
      processed_acc <= 0;
      ld_i_r <= 0;
      rd_i_r <= 0;
      saved_result <= 0;
      ld_o_r <= 0;
      rd_o_r <= 0;
      rd_pointer <= 0;
      wr_pointer <= 0;
      tap_index <= 0;
      state <= CLEAR;
      clear_address <= 0;
      channel <= LEFT;
    end 
    else begin        
      case (state)
        LOAD: begin
          if (valid_i && ready_o) begin
            if (!bypass_r) begin
              ld_i_r <= ld_i;
              rd_i_r <= rd_i;
              state <= WRITE;
            end
            else begin
              ld_o_r <= ld_i;
              rd_o_r <= rd_i;
              state <= DONE;
            end
          end
        end
        
        WRITE: begin
          l_cir_ram[wr_pointer] <= ld_i_r;
          r_cir_ram[wr_pointer] <= rd_i_r;

          wr_pointer <= (wr_pointer == NUM_TAPS-1) ? 0 : wr_pointer + 1;
          rd_pointer <= wr_pointer;
          tap_index <= 0;
          accumulator <= 0;
          channel <= LEFT;
          
          state <= MAC;
        end

        MAC: begin
          if (channel == LEFT) begin 
            accumulator <= accumulator + l_cir_ram[rd_pointer] * selected_coeff;
            rd_pointer <= (rd_pointer == 0) ? (NUM_TAPS-1) : rd_pointer - 1;
          end else if (channel == RIGHT) begin
            accumulator <= accumulator + r_cir_ram[rd_pointer] * selected_coeff;
            rd_pointer <= (rd_pointer == 0) ? (NUM_TAPS-1) : rd_pointer - 1;
          end
 
          tap_index <= tap_index + 1;
          if (tap_index == (NUM_TAPS-1)) begin
            state <= ROUND;
          end
        end
        
        ROUND: begin

          if (accumulator >= 0) begin
            rounded_acc <= (accumulator + ACC_WIDTH'(ROUND_OFFSET)) >>> FRAC_BITS;
          end else if (accumulator < 0) begin
            rounded_acc <= (accumulator + ACC_WIDTH'(ROUND_OFFSET) - 1) >>> FRAC_BITS;
          end
          state <= SAT;
        end
        
        SAT: begin
          if (rounded_acc > max_ext) begin 
            processed_acc <= MAX;  
          end else if (rounded_acc < min_ext) begin
            processed_acc <= MIN;  
          end else begin
            processed_acc <= rounded_acc[WIDTH-1:0];     
          end

          state <= STORE;
        end

        STORE: begin
          if (channel == LEFT) begin
            saved_result <= processed_acc;
            channel <= RIGHT;
            rd_pointer <= (wr_pointer == 0) ? (NUM_TAPS-1) : wr_pointer - 1'b1;           
            tap_index <= 0;
            accumulator <= 0;
            state <= MAC;
          end else if (channel == RIGHT) begin
            ld_o_r <= saved_result;
            rd_o_r <= processed_acc;
            state <= DONE;
          end
        end

        DONE: begin
          if (ready_i) begin
            state <= LOAD;
          end
        end

        CLEAR: begin
          l_cir_ram[clear_address] <= 0;
          r_cir_ram[clear_address] <= 0;

          if (clear_address == NUM_TAPS-1) begin
            clear_address <= 0;
            state <= LOAD;
          end else begin
            clear_address <= clear_address + 1;
          end
        end

        default: begin
          state <= LOAD;
        end
      endcase
    end
end
endmodule


