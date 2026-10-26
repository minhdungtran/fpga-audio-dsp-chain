module delay
#(
    parameter WIDTH = 24,
    parameter FRAC_BITS = 14,
    parameter SAMPLE_F = 48000,
    parameter MAX_DELAY_MS = 500  
)
(
    input logic                         valid_i,       // Pulse high when previous modules have available samples
    input logic                         ready_i,       // Pulse high when the next module can receive samples
    input logic                         dsp_clk,        
    input logic                           reset,
    input logic                          bypass,      // Bypass the delay effect
    input logic         [FRAC_BITS-1:0]    fb_i,      // Configurable feedback value 
    input logic         [FRAC_BITS-1:0]     w_i,      // Configurable wet dry value 
    input logic         [9:0]           delay_i,      // Configurable delay time in ms, based on sample frequency
    input logic signed  [WIDTH-1:0]        ld_i,      // Left channel data flow in 
    input logic signed  [WIDTH-1:0]        rd_i,      // Right channel data flow in 
    
    output logic                        valid_o,      // Pulse high when this module's samples can be sent to next module
    output logic                        ready_o,      // Pulse high this module can accept new samples from previous modules
    output logic signed [WIDTH-1:0]        ld_o,      // Left channel output 
    output logic signed [WIDTH-1:0]        rd_o       // Right channel output
);

localparam C_BUFFER_SIZE = MAX_DELAY_MS*SAMPLE_F/1000;
localparam BUFFER_ADD_WIDTH = $clog2(C_BUFFER_SIZE);
localparam EXTEND = WIDTH + FRAC_BITS;
localparam UNITY = EXTEND'(1<<FRAC_BITS);

localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

typedef enum logic [2:0] {
    LOAD, STORE, DONE, CLEAR
} state_t;

state_t state;

// Configuration and handshake control
logic bypass_r;
logic [FRAC_BITS-1:0] fb_r;
logic [EXTEND-1:0] w_r;
logic [9:0] delay_ms_r;
logic ram_skip;
assign ram_skip = bypass_r || c_buffer_used == 0;
assign valid_o = (state == DONE);
assign ready_o = (state == LOAD) && !reset;

// Circular buffer
logic signed [WIDTH-1:0] c_buffer_left [0:C_BUFFER_SIZE-1];
logic signed [WIDTH-1:0] c_buffer_right [0:C_BUFFER_SIZE-1];
 
logic [BUFFER_ADD_WIDTH-1:0] c_buffer_used;
assign c_buffer_used = BUFFER_ADD_WIDTH'(delay_ms_r*SAMPLE_F/1000);

logic [BUFFER_ADD_WIDTH-1:0] ptr;
logic [BUFFER_ADD_WIDTH-1:0] clear_addr;

// Registers for input samples
logic signed [WIDTH-1:0] ld_i_r, rd_i_r;

// Registers for current old sample
logic signed[WIDTH-1:0] delay_left_r;
logic signed[WIDTH-1:0] delay_right_r;

// Wires for the (old samples * feedback configuration value)
logic signed [EXTEND-1:0] fb_left_w, fb_right_w;
assign fb_left_w = delay_left_r * $signed({1'b0,fb_r});
assign fb_right_w = delay_right_r * $signed({1'b0,fb_r});

// Wires for dry calculation
logic signed [EXTEND-1:0] ld_dry_w, rd_dry_w;
assign ld_dry_w = EXTEND'(ld_i_r) + (fb_left_w >>> FRAC_BITS);
assign rd_dry_w = EXTEND'(rd_i_r) + (fb_right_w >>> FRAC_BITS);

// Wires for data after shifting
logic signed [WIDTH-1:0] ld_dry_sat_w, rd_dry_sat_w;

// Wires for output calculation
logic signed [EXTEND-1:0] ld_mac_w, rd_mac_w;
assign ld_mac_w = ld_i_r*(UNITY-$signed(w_r)) + $signed(w_r)*delay_left_r;
assign rd_mac_w = rd_i_r*(UNITY-$signed(w_r)) + $signed(w_r)*delay_right_r;

// Wires for data after shifting
logic signed [EXTEND-1:0] ld_shift_w, rd_shift_w;
assign ld_shift_w = ld_mac_w >>> FRAC_BITS;
assign rd_shift_w = rd_mac_w >>> FRAC_BITS;

// Wires for saturation check
logic signed [WIDTH-1:0] ld_sat_w, rd_sat_w;

// Registers for output
logic signed [WIDTH-1:0] ld_o_r, rd_o_r;
assign ld_o = ld_o_r;
assign rd_o = rd_o_r;

// Combinational logic for saturation check
always_comb begin
    // for output calculation
    if ((ld_shift_w) > (EXTEND'(MAX))) begin 
        ld_sat_w = MAX;
    end else if ((ld_shift_w) < (EXTEND'(MIN))) begin 
        ld_sat_w = MIN;
    end else begin
          ld_sat_w = WIDTH'(ld_shift_w);
    end

    if ((rd_shift_w) > (EXTEND'(MAX))) begin 
        rd_sat_w = MAX;
    end else if ((rd_shift_w) < (EXTEND'(MIN))) begin 
        rd_sat_w = MIN;
    end else begin
          rd_sat_w = WIDTH'(rd_shift_w);
    end

    // for dry calculation
    if ((ld_dry_w) > (EXTEND'(MAX))) begin 
        ld_dry_sat_w = MAX;
    end else if ((ld_dry_w) < (EXTEND'(MIN))) begin 
        ld_dry_sat_w = MIN;
    end else begin
          ld_dry_sat_w = WIDTH'(ld_dry_w);
    end

    if ((rd_dry_w) > (EXTEND'(MAX))) begin 
        rd_dry_sat_w = MAX;
    end else if ((rd_dry_w) < (EXTEND'(MIN))) begin 
        rd_dry_sat_w = MIN;
    end else begin
          rd_dry_sat_w = WIDTH'(rd_dry_w);
    end
end

always_ff @(posedge dsp_clk) begin
    if (reset) begin
        delay_left_r <= 0;
        delay_right_r <= 0;
        ld_i_r <= 0;
        rd_i_r <= 0;
        ld_o_r <= 0;
        rd_o_r <= 0;
        ptr <= 0;
        fb_r <= fb_i;
        w_r <= EXTEND'(w_i);
        bypass_r <= bypass;
        clear_addr <= 0;
        state <= CLEAR;

        if (delay_i > MAX_DELAY_MS) begin
            delay_ms_r <= 10'(MAX_DELAY_MS);
        end else begin
            delay_ms_r <= delay_i;
        end

    end
    else begin 
        case (state)
            LOAD: begin
                if (valid_i && ready_o) begin
                    ld_i_r <= ld_i;
                    rd_i_r <= rd_i;
                    if (!ram_skip) begin
                        delay_left_r <= c_buffer_left[ptr];
                        delay_right_r <= c_buffer_right[ptr];
                        state <= STORE;
                    end else begin
                        ld_o_r <= ld_i;
                        rd_o_r <= rd_i;
                        state <= DONE;
                    end
                end
            end

            STORE: begin
                c_buffer_left[ptr] <= ld_dry_sat_w;
                c_buffer_right[ptr] <= rd_dry_sat_w;
                ptr <= (ptr == c_buffer_used - 1'b1 ) ? 0 : ptr + 1'b1;
                ld_o_r <= ld_sat_w;
                rd_o_r <= rd_sat_w;  
                              
                state <= DONE;
            end
    
            DONE: begin
                if (ready_i) begin
                    state <= LOAD;
                end
            end

            CLEAR: begin
                c_buffer_left[clear_addr] <= 0;
                c_buffer_right[clear_addr] <= 0;

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
