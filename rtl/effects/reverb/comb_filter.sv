module comb_filter
#(
    parameter WIDTH = 24,
    parameter FRAC_BITS = 14,
    parameter COMB_ID = 0,
    parameter MAX_DECAY = 50,
    parameter string G_MEM_FILE = "coefficients/reverb/mem/comb_0_g.mem"
)
(
    input logic                          valid_i,       // Pulse high when previous modules have available samples
    input logic                          ready_i,       // Pulse high when the next module can receive samples
    input logic                          dsp_clk,        
    input logic                            reset,
    input logic         [1:0]             room_i,      // Configurable room size
    input logic         [5:0]           decay_60,      // Time required for the reverb amplitude to decrease by 60 dB
    input logic signed  [WIDTH-1:0]         ld_i,      // Left channel data flow in 
    input logic signed  [WIDTH-1:0]         rd_i,      // Right channel data flow in 
    
    output logic                         valid_o,      // Pulse high when this module's samples can be sent to next module
    output logic                         ready_o,      // Pulse high this module can accept new samples from previous modules
    output logic signed [WIDTH-1:0]         ld_o,      // Left channel output 
    output logic signed [WIDTH-1:0]         rd_o       // Right channel output
);

localparam int C_BUFFER_SIZE =
    (COMB_ID == 0) ? 1783 :
    (COMB_ID == 1) ? 2227 :
    (COMB_ID == 2) ? 2467 :
                     2623;

localparam BUFFER_ADD_WIDTH = $clog2(C_BUFFER_SIZE);
localparam EXTEND = WIDTH + FRAC_BITS;

localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};
            
typedef enum logic [3:0] {
    LOAD, MULTIPLICATION, SUM, SCALE, SAT, STORE, DONE, CLEAR
} state_t;

typedef enum logic {
    LEFT, RIGHT
} channel_t;

state_t state;
channel_t channel;

// Configuration
logic [1:0] room_type;
logic [11:0] delay_samples_nbr;
logic [5:0] decay_r;

room_lut #(
    .COMB_ID(COMB_ID)
) room_u(
    .room_size(room_type),
    .delay_samples_nbr(delay_samples_nbr)
);
//g value
localparam int G_ROM_DEPTH = 3 * (MAX_DECAY + 1);
localparam int G_ADDRESS_WIDTH = $clog2(G_ROM_DEPTH);

logic [FRAC_BITS-1:0] g_rom [0:G_ROM_DEPTH-1];
logic [G_ADDRESS_WIDTH-1:0] g_address;

logic [FRAC_BITS-1:0] g_r;
assign g_address = room_type * (MAX_DECAY +1) + (G_ADDRESS_WIDTH)'(decay_r);

initial begin 
    $readmemh(G_MEM_FILE, g_rom);
end

// Handshake control
assign valid_o = (state == DONE);
assign ready_o = (state == LOAD) && !reset;

// BRAM 
logic [BUFFER_ADD_WIDTH-1:0] ptr;
logic [BUFFER_ADD_WIDTH-1:0] clear_addr;

// Registers for input samples
logic signed [WIDTH-1:0] input_r;
logic signed [WIDTH-1:0] right_pending_r;

// Registers and wire for the delay
logic signed [WIDTH-1:0] delay_w;
logic signed [WIDTH-1:0] left_ram_data, right_ram_data;
assign delay_w = (channel == LEFT) ? left_ram_data : right_ram_data;

// Registers for r*g
logic signed[EXTEND-1:0] fb_product_r;

// Registers for scaling
logic signed [EXTEND-1:0]  fb_scaled_r;

// Registes before saturation check
logic signed [EXTEND-1:0] fb_sum_raw_r;

// Registes after saturation check
logic signed [WIDTH-1:0] fb_sum_sat_r;

// Registers for output
logic signed [WIDTH-1:0] ld_o_r, rd_o_r;
assign ld_o = ld_o_r;
assign rd_o = rd_o_r;

logic left_we, right_we;
logic [BUFFER_ADD_WIDTH-1:0] left_waddr, right_waddr;
logic signed [WIDTH-1:0] left_wdata, right_wdata;

audio_bram #(
    .WIDTH(WIDTH),
    .DEPTH(C_BUFFER_SIZE)
) left_bram (
    .clk(dsp_clk),
    .rd_addr(ptr),
    .rd_data(left_ram_data),
    .wr_addr(left_waddr),
    .wr_data(left_wdata),
    .wr_en(left_we)
);

always_comb begin
    left_we    = 1'b0;
    left_waddr = ptr;
    left_wdata = fb_sum_sat_r;

    if (!reset && state == CLEAR) begin
        left_we    = 1'b1;
        left_waddr = clear_addr;
        left_wdata = '0;
    end
    else if (!reset && state == STORE && channel == LEFT) begin
        left_we = 1'b1;
    end
end

audio_bram #(
    .WIDTH(WIDTH),
    .DEPTH(C_BUFFER_SIZE)
) right_bram (
    .clk(dsp_clk),
    .rd_addr(ptr),
    .rd_data(right_ram_data),
    .wr_addr(right_waddr),
    .wr_data(right_wdata),
    .wr_en(right_we)
);

always_comb begin
    right_we    = 1'b0;
    right_waddr = ptr;
    right_wdata = fb_sum_sat_r;

    if (!reset && state == CLEAR) begin
        right_we    = 1'b1;
        right_waddr = clear_addr;
        right_wdata = '0;
    end
    else if (!reset && state == STORE && channel == RIGHT) begin
        right_we = 1'b1;
    end
end

always_ff @(posedge dsp_clk) begin
    if (reset) begin
        room_type <= room_i;
        decay_r <= decay_60;
        input_r <= 0;
        right_pending_r <= 0;
        fb_product_r <= 0;
        fb_scaled_r <= 0;
        fb_sum_raw_r <= 0;
        fb_sum_sat_r <= 0;
        ptr <= 0;
        clear_addr <= 0;
        ld_o_r <= 0;
        rd_o_r <= 0;
        g_r <= 0;
        channel <= LEFT;
        state <= CLEAR;
    end
    else begin
        case(state) 
            LOAD: begin
                if (valid_i && ready_o) begin
                    input_r <= ld_i;
                    right_pending_r <= rd_i;
                    g_r <= g_rom[g_address];
                    channel <= LEFT; 
                    state <= MULTIPLICATION;
                end
            end

            MULTIPLICATION: begin
                fb_product_r <= $signed({1'b0,g_r}) * delay_w; 
                state <= SCALE;
            end
            
            SCALE: begin
                fb_scaled_r <= fb_product_r >>> FRAC_BITS;
                state <= SUM;
            end

            SUM: begin
                fb_sum_raw_r <= EXTEND'(input_r) + fb_scaled_r;
                state <= SAT;
            end
            
            SAT: begin 
                if ((fb_sum_raw_r) > (EXTEND'(MAX))) begin 
                    fb_sum_sat_r <= MAX;
                end else if ((fb_sum_raw_r) < (EXTEND'(MIN))) begin 
                    fb_sum_sat_r <= MIN;
                end else begin
                    fb_sum_sat_r <= WIDTH'(fb_sum_raw_r);
                end
                state <= STORE;
            end

            STORE: begin
                if (channel == LEFT) begin 
                    ld_o_r <= delay_w;
                    input_r <= right_pending_r;
                    
                    channel <= RIGHT;
                    state <= MULTIPLICATION;
                end else begin
                    rd_o_r <= delay_w;
                    ptr <= (ptr ==  BUFFER_ADD_WIDTH'(delay_samples_nbr - 1) ) ? 0 : ptr + 1'b1;    
                    state <= DONE;
                end
            end

            DONE: begin
                if (ready_i) begin
                    state <= LOAD;
                end
            end

            CLEAR: begin
                if (clear_addr == BUFFER_ADD_WIDTH'(C_BUFFER_SIZE - 1)) begin
                    clear_addr <= 0;
                    state <= LOAD;
                end else begin
                    clear_addr <= clear_addr + 1;
                end              
            end

            default: state <= LOAD;
        endcase
    end   
end
endmodule
