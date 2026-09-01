
module dsp_amp
#(
    parameter WIDTH = 24,
    parameter G_length = 16
)
(
    input wire                shared_sck,       
    input wire                shared_WS,        
    input wire                shared_SD,        
    input wire                shared_reset, 

    input wire [G_length-1:0] shared_G,

    output wire               output_SD
       
);

wire [WIDTH-1:0] RV_AMP_LD;
wire [WIDTH-1:0] RV_AMP_RD;
wire [WIDTH-1:0] AMP_TX_LD;
wire [WIDTH-1:0] AMP_TX_RD;
wire             RV_AMP_DATA;
wire             AMP_TX_DATA;
 
i2s_rv receiver(
    .sck(shared_sck),
    .WS(shared_WS),
    .SD(shared_SD),
    .reset(shared_reset),
    .data_ready(RV_AMP_DATA),
    .output_LD(RV_AMP_LD),
    .output_RD(RV_AMP_RD)
);

amplifier u_amplifier(
    .data_valid(RV_AMP_DATA),
    .data_ready(AMP_TX_DATA),
    .sck(shared_sck),
    .reset(shared_reset),
    .in_LD(RV_AMP_LD),
    .in_RD(RV_AMP_RD),
    .G(shared_G),
    .out_LD(AMP_TX_LD),
    .out_RD(AMP_TX_RD)
);

i2s_tx transmitter(
    .sck(shared_sck),
    .WS(shared_WS),
    .input_LD(AMP_TX_LD),
    .input_RD(AMP_TX_RD),
    .reset(shared_reset),
    .data_valid(AMP_TX_DATA),
    .SD(output_SD)
);
endmodule