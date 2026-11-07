module dsp_fir
#(
    parameter WIDTH = 24,
    parameter BIT_SLOT = 32,
    parameter COEFF_WIDTH = 16,
    parameter FRAC_BITS = 15,
    parameter NUM_TAPS = 63,
    parameter ADDR_WIDTH = 3
)
(
    input logic i2s_clk, dsp_clk,
    input logic i2s_reset, dsp_reset,
    input logic ws,
    input logic sd_i,

    input logic bypass,
    input logic [1:0] mode_i,

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

// Wires between receiver and fifo 1
logic rx_valid_o;
logic [WIDTH-1:0] ld_rx, rd_rx;

logic fifo1_wr_en;
assign fifo1_wr_en = rx_valid_o && rx_ready_o;

logic [BIT_SLOT*2-1:0] fifo1_d_in;
assign fifo1_d_in = {BIT_SLOT'(ld_rx), BIT_SLOT'(rd_rx)};


// Wires between fifo 1 and fir

logic full1, empty1;
logic fir_valid_i, fir_ready_o;

assign fir_valid_i = (state1 == SEND) && !dsp_reset;

logic fifo1_rd_en ;
assign fifo1_rd_en = !empty1 && (state1 == CHECK) && !dsp_reset;

assign rx_fifo_overflow = full1 && rx_valid_o;

always_ff @(posedge dsp_clk) begin
    if (dsp_reset) begin
        chain_ready_o <= 0;
        state1 <= CHECK;
    end else begin 
        if (fir_ready_o) begin
            chain_ready_o <= 1;
        end

        case (state1)
            CHECK: begin
                if (!empty1) begin
                    state1 <= SEND;
                end
            end

            SEND: begin
                if (fir_ready_o) begin
                    state1 <= CHECK;
                end
            end
        
            default: begin
                state1 <= CHECK;
            end
        endcase
    end
end

logic [WIDTH-1:0] fir_ld_i, fir_rd_i;
logic [BIT_SLOT*2-1:0] fifo1_d_out;
assign fir_ld_i = fifo1_d_out[BIT_SLOT+WIDTH-1:BIT_SLOT];
assign fir_rd_i = fifo1_d_out[WIDTH-1:0];

// Wires between fir and fifo 2
logic full2, empty2;
logic fir_valid_o, fir_ready_i;
assign fir_ready_i = !full2;

logic fifo2_wr_en;
assign fifo2_wr_en = fir_valid_o && fir_ready_i;

logic [WIDTH-1:0] fir_ld_o, fir_rd_o;
logic [BIT_SLOT*2-1:0] fifo2_d_in;
assign fifo2_d_in = {BIT_SLOT'(fir_ld_o), BIT_SLOT'(fir_rd_o)};

//Wires between fifo 2 and tx
logic tx_valid_i, tx_ready_o;
assign tx_valid_i = (state2 == SEND);

logic fifo2_rd_en;
assign fifo2_rd_en = (state2 == CHECK) && !empty2 && !i2s_reset;
assign ready_o = tx_ready_o;

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

logic [WIDTH-1:0] tx_ld_i, tx_rd_i;
logic [BIT_SLOT*2-1:0] fifo2_d_out;
assign tx_ld_i = fifo2_d_out[BIT_SLOT+WIDTH-1:BIT_SLOT];
assign tx_rd_i = fifo2_d_out[WIDTH-1:0];

i2s_rx #(
    .WIDTH(WIDTH)
) rx_u(
    .sck(i2s_clk),
    .WS(ws),
    .SD(sd_i),
    .reset(i2s_reset),
    .valid_o(rx_valid_o),
    .ld_o(ld_rx),
    .rd_o(rd_rx)
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

fir #(
    .WIDTH(WIDTH),
    .FRAC_BITS(FRAC_BITS),
    .COEFF_WIDTH(COEFF_WIDTH),
    .NUM_TAPS(NUM_TAPS)
) fir_u(
    .valid_i(fir_valid_i), 
    .ready_i(fir_ready_i),
    .dsp_clk(dsp_clk),
    .reset(dsp_reset),
    .bypass(bypass),
    .mode_i(mode_i),
    .ld_i(fir_ld_i),
    .rd_i(fir_rd_i),
    .valid_o(fir_valid_o),
    .ready_o(fir_ready_o),
    .ld_o(fir_ld_o),
    .rd_o(fir_rd_o)
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
