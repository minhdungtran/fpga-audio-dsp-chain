module dsp_chain
#(
    parameter WIDTH = 24,
    parameter BIT_SLOT = 32,
    parameter COEFF_WIDTH = 16,
    parameter FIR_FRAC_BITS = 15,
    parameter FRAC_BITS = 14,
    parameter NUM_TAPS = 63,
    parameter GAIN_LENGTH = FRAC_BITS + 2,
    parameter SAMPLE_F = 48,
    parameter MAX_DELAY_MS = 500,
    parameter MAX_DECAY = 50,
    parameter ADDR_WIDTH = 3
)
(
    input logic i2s_clk, dsp_clk,
    input logic i2s_reset, dsp_reset,
    input logic ws,
    input logic sd_i,

    // amp configuration
    input logic amp_bypass,
    input logic [GAIN_LENGTH-1:0] g, 

    // fir configuration
    input logic fir_bypass,
    input logic [1:0] mode_i,

    // delay configuration
    input logic delay_bypass,
    input logic [FRAC_BITS-1:0] fb_i, delay_w_i,
    input logic [9:0] delay_i,

    // reverb configuration
    input logic                 reverb_bypass,
    input logic [1:0]                  room_i,      
    input logic [5:0]                decay_60,     
    input logic [FRAC_BITS-1:0]    reverb_w_i,      
    input logic [FRAC_BITS-1:0]   diffusion_i, 

    output logic rx_fifo_overflow,
    output logic chain_ready_o,     // Pulse high when the initialization of the whole chain is completed
    output logic sd_o,
    output logic ready_o      
);


typedef enum logic {
    CHECK, SEND
} state_read;

state_read state1, state2;

// chain_ready_o synchronized to i2s clock
logic rx_ready_o;

// Receiver data and handshake
logic rx_valid_o;
logic [WIDTH-1:0] rx_ld, rx_rd;

// FIFO 1
logic full1, empty1;

logic fifo1_rd_en, fifo1_wr_en;
assign fifo1_wr_en = rx_valid_o && rx_ready_o;
assign fifo1_rd_en = !empty1 && (state1 == CHECK) && !dsp_reset;

logic [BIT_SLOT*2-1:0] fifo1_d_in, fifo1_d_out;
assign fifo1_d_in = {BIT_SLOT'(rx_ld), BIT_SLOT'(rx_rd)};


// Amplifier data
logic [WIDTH-1:0] amp_ld_i, amp_rd_i;
logic [WIDTH-1:0] amp_ld_o, amp_rd_o;
assign amp_ld_i = fifo1_d_out[BIT_SLOT+WIDTH-1:BIT_SLOT];
assign amp_rd_i = fifo1_d_out[WIDTH-1:0];

// Amplifier Handshake
logic amp_valid_i, amp_ready_i;
logic amp_valid_o, amp_ready_o;
assign amp_valid_i = (state1 == SEND) && !dsp_reset;
assign rx_fifo_overflow = full1 && rx_valid_o;

// FIR data
logic [WIDTH-1:0] fir_ld_i, fir_rd_i;
assign fir_ld_i = amp_ld_o;
assign fir_rd_i = amp_rd_o;

logic [WIDTH-1:0] fir_ld_o, fir_rd_o;

// FIR handshake
logic fir_valid_i, fir_ready_i;
logic fir_valid_o, fir_ready_o;
assign amp_ready_i = fir_ready_o;
assign fir_valid_i = amp_valid_o;

// Delay data
logic [WIDTH-1:0] delay_ld_i, delay_rd_i;
assign delay_ld_i = fir_ld_o;
assign delay_rd_i = fir_rd_o;

logic [WIDTH-1:0] delay_ld_o, delay_rd_o;

// Delay handshake
logic delay_valid_i, delay_ready_i;
logic delay_valid_o, delay_ready_o;
assign fir_ready_i = delay_ready_i;
assign delay_valid_i = fir_valid_o;

// Reverb data
logic [WIDTH-1:0] reverb_ld_i, reverb_rd_i;
assign reverb_ld_i = delay_ld_o;
assign reverb_rd_i= delay_rd_o;

logic [WIDTH-1:0] reverb_ld_o, reverb_rd_o;

// Reverb handshake
logic reverb_valid_i, reverb_ready_i;
logic reverb_valid_o, reverb_ready_o;
assign delay_ready_i = reverb_ready_o;
assign reverb_valid_i = delay_valid_o;

// FIFO 2
logic full2, empty2;

logic fifo2_wr_en, fifo2_rd_en;
assign fifo2_rd_en = (state2 == CHECK) && !empty2 && !i2s_reset;
assign fifo2_wr_en = reverb_valid_o && reverb_ready_i;

assign reverb_ready_i = !full2;

logic [BIT_SLOT*2-1:0] fifo2_d_in, fifo2_d_out;

assign fifo2_d_in = {BIT_SLOT'(reverb_ld_o), BIT_SLOT'(reverb_rd_o)};

// Transmitter data
logic [WIDTH-1:0] tx_ld_i, tx_rd_i;

assign tx_ld_i = fifo2_d_out[BIT_SLOT+WIDTH-1:BIT_SLOT];
assign tx_rd_i = fifo2_d_out[WIDTH-1:0];

// Transmitter handshake
logic tx_valid_i;
logic tx_ready_o;

assign tx_valid_i = (state2 == SEND);
assign ready_o = tx_ready_o;

// Chain initialization
logic chain_intialized;
assign chain_intialized = amp_ready_o && fir_ready_o && delay_ready_o && reverb_ready_o;

always_ff @(posedge dsp_clk) begin
    if (dsp_reset) begin
        chain_ready_o <= 0;
        state1 <= CHECK;
    end else begin 
        if (chain_intialized) begin
            chain_ready_o <= 1;
        end

        case (state1)
            CHECK: begin
                if (!empty1) begin
                    state1 <= SEND;
                end
            end

            SEND: begin
                if (amp_ready_o) begin
                    state1 <= CHECK;
                end
            end
        
            default: begin
                state1 <= CHECK;
            end
        endcase
    end
end

always_ff @(posedge i2s_clk) begin
    if (i2s_reset) begin
        state2 <= CHECK;
    end else begin
        case (state2) 
            CHECK: begin
                if (!empty2) begin
                    state2 <= SEND;
                end
            end

            SEND: begin
                if (tx_ready_o) begin
                    state2 <= CHECK;
                end
            end

            default: begin
                state2 <= CHECK;
            end
        endcase
    end
end

i2s_rx #(
    .WIDTH(WIDTH)
) rx_u(
    .sck(i2s_clk),
    .WS(ws),
    .SD(sd_i),
    .reset(i2s_reset),
    .valid_o(rx_valid_o),
    .ld_o(rx_ld),
    .rd_o(rx_rd)
);

async_fifo #(
    .WIDTH(BIT_SLOT*2),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(ADDR_WIDTH+1)
) rx_fifo(
    .rd_clk(dsp_clk),
    .rd_reset(dsp_reset),
    .rd_en(fifo1_rd_en),
    .wr_clk(i2s_clk),
    .wr_reset(i2s_reset),
    .wr_en(fifo1_wr_en),
    .full(full1),
    .empty(empty1),
    .d_in(fifo1_d_in),
    .d_out(fifo1_d_out)
);

amplifier #(
    .WIDTH(WIDTH),
    .GAIN_LENGTH(GAIN_LENGTH)
) amp_u (
    .valid_i(amp_valid_i),      
    .ready_i(amp_ready_i),      
    .dsp_clk(dsp_clk),        
    .reset(dsp_reset),
    .bypass(amp_bypass),
    .g(g),      
    .ld_i(amp_ld_i),      
    .rd_i(amp_rd_i),      
    
    .valid_o(amp_valid_o),      
    .ready_o(amp_ready_o),      
    .ld_o(amp_ld_o),    
    .rd_o(amp_rd_o)     
);

fir #(
    .WIDTH(WIDTH),
    .FRAC_BITS(FIR_FRAC_BITS),
    .COEFF_WIDTH(COEFF_WIDTH),
    .NUM_TAPS(NUM_TAPS)
) fir_u(
    .valid_i(fir_valid_i), 
    .ready_i(fir_ready_i),
    .dsp_clk(dsp_clk),
    .reset(dsp_reset),
    .bypass(fir_bypass),
    .mode_i(mode_i),
    .ld_i(fir_ld_i),
    .rd_i(fir_rd_i),
    .valid_o(fir_valid_o),
    .ready_o(fir_ready_o),
    .ld_o(fir_ld_o),
    .rd_o(fir_rd_o)
);

delay #(
    .WIDTH(WIDTH),
    .FRAC_BITS(FRAC_BITS),
    .SAMPLE_F(SAMPLE_F),
    .MAX_DELAY_MS(MAX_DELAY_MS)
) delay_u(
    .valid_i(delay_valid_i), 
    .ready_i(delay_ready_i),
    .dsp_clk(dsp_clk),
    .reset(dsp_reset),
    .bypass(delay_bypass),
    .fb_i(fb_i),
    .w_i(delay_w_i),
    .delay_i(delay_i),
    .ld_i(delay_ld_i),
    .rd_i(delay_rd_i),
    .valid_o(delay_valid_o),
    .ready_o(delay_ready_o),
    .ld_o(delay_ld_o),
    .rd_o(delay_rd_o)
);

reverb #(
    .WIDTH(WIDTH),
    .FRAC_BITS(FRAC_BITS),
    .MAX_DECAY(MAX_DECAY)
) reverb_u(
    .valid_i(reverb_valid_i),
    .ready_i(reverb_ready_i),
    .dsp_clk(dsp_clk),
    .reset(dsp_reset),
    .bypass(reverb_bypass),
    .room_i(room_i),  
    .decay_60(decay_60),
    .w_i(reverb_w_i),     
    .diffusion_i(diffusion_i),   
    .ld_i(reverb_ld_i),
    .rd_i(reverb_rd_i),
    .valid_o(reverb_valid_o),
    .ready_o(reverb_ready_o),
    .ld_o(reverb_ld_o),
    .rd_o(reverb_rd_o)
);

async_fifo #(
    .WIDTH(BIT_SLOT*2),
    .ADDR_WIDTH(ADDR_WIDTH),
    .PTR_WIDTH(ADDR_WIDTH+1)
) tx_fifo(
    .rd_clk(i2s_clk),
    .rd_reset(i2s_reset),
    .rd_en(fifo2_rd_en),
    .wr_clk(dsp_clk),
    .wr_reset(dsp_reset),
    .wr_en(fifo2_wr_en),
    .full(full2),
    .empty(empty2),
    .d_in(fifo2_d_in),
    .d_out(fifo2_d_out)
);

i2s_tx #(
    .WIDTH(WIDTH)
) tx_u(
    .sck(i2s_clk),
    .reset(i2s_reset),
    .WS(ws),
    .valid_i(tx_valid_i),
    .ld_i(tx_ld_i),
    .rd_i(tx_rd_i),
    .ready_o(tx_ready_o),
    .SD(sd_o)
);

synchronizer #(
    .PTR_WIDTH(1)
) chain_ready_sync (
    .clk(i2s_clk),
    .reset(i2s_reset),
    .d_in(chain_ready_o),
    .q_2(rx_ready_o)
);

endmodule
