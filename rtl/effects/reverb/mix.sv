module mix
#(
    parameter WIDTH = 24,
    parameter FRAC_BITS = 14
)
(
    input logic                         valid_i,       // Pulse high when previous modules have available samples
    input logic                         ready_i,       // Pulse high when the next module can receive samples
    input logic                         dsp_clk,        
    input logic                           reset,
    input logic         [FRAC_BITS-1:0]     w_i,        // Configurable wet dry value 
    input logic signed  [WIDTH-1:0]  w_data_left,       // Left wet samples
    input logic signed  [WIDTH-1:0] w_data_right,       // Right wet samples
    input logic signed  [WIDTH-1:0]         ld_i,       // Left channel input
    input logic signed  [WIDTH-1:0]         rd_i,       // Right channel input
    
    output logic                        valid_o,      // Pulse high when this module's samples can be sent to next module
    output logic                        ready_o,      // Pulse high this module can accept new samples from previous modules
    output logic signed [WIDTH-1:0]        ld_o,      // Left channel output 
    output logic signed [WIDTH-1:0]        rd_o       // Right channel output
);

localparam EXTEND = WIDTH + FRAC_BITS;

localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

typedef enum logic [2:0] {
    LOAD, DIFF, SUM, SAT, STORE, DONE
} state_t;

typedef enum logic {
    LEFT, RIGHT
} channel_t;

state_t state;
channel_t channel;

// Configuration
logic [FRAC_BITS-1:0] w_r;

// Handshake control
assign valid_o = (state == DONE);
assign ready_o = (state == LOAD) && !reset;
 
// Registers for input samples
logic signed [WIDTH-1:0] input_r;
logic signed [WIDTH-1:0] right_pending_r;

// Registers for wet samples
logic signed [WIDTH-1:0] wet_data_r;
logic signed [WIDTH-1:0] right_wet_data_pending;

// Registers for r-x
logic signed [WIDTH:0] diff_r;

// Wire for wet unscaled
logic signed [EXTEND+1:0] wet_unscaled_w;
assign wet_unscaled_w = diff_r*$signed({1'b0, w_r});

// Registes before saturation check
logic signed [EXTEND-1:0] output_raw_r;

// Registes after saturation check
logic signed [WIDTH-1:0] output_sat_r;

// Registers for output
logic signed [WIDTH-1:0] ld_o_r, rd_o_r;
assign ld_o = ld_o_r;
assign rd_o = rd_o_r;

always_ff @(posedge dsp_clk) begin
    if (reset) begin
        right_pending_r <= 0;
        input_r <= 0;
        wet_data_r <= 0;
        right_wet_data_pending <= 0;
        diff_r <= 0;
        output_raw_r <= 0;
        output_sat_r <= 0;
        ld_o_r <= 0;
        rd_o_r <= 0;
        w_r <= w_i;
        channel <= LEFT;
        state <= LOAD;
    end

    else begin 
        case (state)
            LOAD: begin
                if (valid_i && ready_o) begin
                    input_r <= ld_i;
                    right_pending_r <= rd_i;
                    wet_data_r <= w_data_left;
                    right_wet_data_pending <= w_data_right;
                    channel <= LEFT;
                    state <= DIFF;
                end
            end

            DIFF: begin // calculate r-x for output and r*g for feedback
                diff_r <= $signed({wet_data_r[WIDTH-1], wet_data_r}) - $signed({input_r[WIDTH-1], input_r});
                state <= SUM;
            end

            SUM: begin //scale and clip diff*w product
                output_raw_r <=EXTEND'(EXTEND'(input_r) + (wet_unscaled_w >>> FRAC_BITS));
                state <= SAT;
            end

            SAT: begin
                if ((output_raw_r) > (EXTEND'(MAX))) begin 
                    output_sat_r <= MAX;
                end else if ((output_raw_r) < (EXTEND'(MIN))) begin 
                    output_sat_r <= MIN;
                end else begin
                    output_sat_r <= WIDTH'(output_raw_r);
                end

                state <= STORE;
            end

            STORE: begin
                if (channel == LEFT) begin 
                    ld_o_r <= output_sat_r;
                    input_r <= right_pending_r;
                    wet_data_r <= right_wet_data_pending;
                    channel <= RIGHT;
                    state <= DIFF;
                end else begin
                    rd_o_r <= output_sat_r;
                    state <= DONE;
                end
            end

            DONE: begin
                if (ready_i) begin
                    state <= LOAD;
                end
            end

            default: state <= LOAD;
        endcase
    end   
end
endmodule
