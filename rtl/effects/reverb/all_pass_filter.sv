module all_pass_filter
#(
    parameter WIDTH = 24,
    parameter FRAC_BITS = 14,
    parameter ALL_PASS_ID = 0  
)
(
    input logic                             valid_i,       // Pulse high when previous modules have available samples
    input logic                             ready_i,       // Pulse high when the next module can receive samples
    input logic                             dsp_clk,        
    input logic                               reset,
    input logic         [FRAC_BITS-1:0] diffusion_i,      // Configurable feedback value 
    input logic signed  [WIDTH-1:0]            ld_i,      // Left channel data flow in 
    input logic signed  [WIDTH-1:0]            rd_i,      // Right channel data flow in 
    
    output logic                            valid_o,      // Pulse high when this module's samples can be sent to next module
    output logic                            ready_o,      // Pulse high this module can accept new samples from previous modules
    output logic signed [WIDTH-1:0]            ld_o,      // Left channel output 
    output logic signed [WIDTH-1:0]            rd_o       // Right channel output
);

localparam C_BUFFER_SIZE = 
    (ALL_PASS_ID == 0) ? 240 :
    (ALL_PASS_ID == 1) ? 82  :
                         240;
                         
localparam BUFFER_ADD_WIDTH = $clog2(C_BUFFER_SIZE);
localparam EXTEND = WIDTH + FRAC_BITS;

localparam signed [WIDTH-1:0] MAX = {1'b0, {(WIDTH-1){1'b1}}};
localparam signed [WIDTH-1:0] MIN = {1'b1, {(WIDTH-1){1'b0}}};

typedef enum logic [4:0] {
    LOAD, FB, FB_SUM, FB_SAT, FF, FF_SUM, FF_SAT, STORE, DONE, CLEAR
} state_t;

typedef enum logic {
    LEFT, RIGHT
} channel_t;

state_t state;
channel_t channel;

// Configuration
logic [FRAC_BITS-1:0] diffusion_r;

// Handshake flag
assign valid_o = (state == DONE);
assign ready_o = (state == LOAD) && !reset;
 
logic [BUFFER_ADD_WIDTH-1:0] ptr;
logic [BUFFER_ADD_WIDTH-1:0] clear_addr;

// Registers for input samples
logic signed [WIDTH-1:0] input_r;
logic signed [WIDTH-1:0] right_pending_r;

// Registers and wire for the delay
logic signed [WIDTH-1:0] delay_r;
logic signed [WIDTH-1:0] left_ram_data, right_ram_data;

// Registers for product a*r[n-D] and a*r[n]
logic signed [EXTEND-1:0] fb_product_r;
logic signed [EXTEND-1:0] ff_product_r;

// Registes before saturation check
logic signed [EXTEND-1:0] output_raw_r;
logic signed [EXTEND-1:0] fb_sum_raw_r;

// Registes after saturation check
logic signed [WIDTH-1:0] output_sat_r;
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
        right_pending_r <= 0;
        input_r <= 0;
        delay_r <= 0;
        ff_product_r <= 0;
        fb_product_r <= 0;
        output_raw_r <= 0;
        fb_sum_raw_r <= 0;
        output_sat_r <= 0;
        fb_sum_sat_r <= 0;
        ld_o_r <= 0;
        rd_o_r <= 0;
        ptr <= 0;
        diffusion_r <= diffusion_i;
        clear_addr <= 0;
        channel <= LEFT;
        state <= CLEAR;
    end

    else begin 
        case (state)
            LOAD: begin
                if (valid_i && ready_o) begin
                    input_r <= ld_i;
                    right_pending_r <= rd_i;
                    delay_r <= left_ram_data;
                    channel <= LEFT;
                    state <= FB;
                end
            end

            FB: begin // calculate a*r[n-D] scaled
                fb_product_r <= (delay_r*$signed({1'b0,diffusion_r})) >>> FRAC_BITS;
                state <= FB_SUM;
            end

            FB_SUM: begin 
                fb_sum_raw_r <= EXTEND'(input_r) + fb_product_r;
                state <= FB_SAT;
            end
            
            FB_SAT: begin
                if ((fb_sum_raw_r) > (EXTEND'(MAX))) begin 
                    fb_sum_sat_r <= MAX;
                end else if ((fb_sum_raw_r) < (EXTEND'(MIN))) begin 
                    fb_sum_sat_r <= MIN;
                end else begin
                    fb_sum_sat_r <= WIDTH'(fb_sum_raw_r);
                end
                state <= FF;
            end

            FF: begin
                ff_product_r <= (fb_sum_sat_r*$signed({1'b0,diffusion_r})) >>> FRAC_BITS;
                state <= FF_SUM;
            end

            FF_SUM: begin
                output_raw_r <= EXTEND'(delay_r) - ff_product_r;
                state <= FF_SAT;
            end

            FF_SAT: begin
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
                    delay_r <= right_ram_data;
                    channel <= RIGHT;
                    state <= FB;
                end else begin
                    rd_o_r <= output_sat_r;
                    ptr <= (ptr == (BUFFER_ADD_WIDTH)'(C_BUFFER_SIZE) - 1'b1 ) ? 0 : ptr + 1'b1;    
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
