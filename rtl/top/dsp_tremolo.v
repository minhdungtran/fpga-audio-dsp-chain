module dsp_tremolo
#(
    parameter WIDTH = 24
)
(
    input wire                shared_sck,       
    input wire                shared_WS,        
    input wire                shared_SD,        
    input wire                shared_reset, 
    
    input wire [15:0]         shared_control_rate,
    input wire [13:0]         shared_control_depth,

    output wire               output_SD
       
);

wire [WIDTH-1:0] RV_LFO_LD;
wire [WIDTH-1:0] RV_LFO_RD;
wire [WIDTH-1:0] LFO_AMP_LD;
wire [WIDTH-1:0] LFO_AMP_RD;
wire [WIDTH-1:0] AMP_TX_LD;
wire [WIDTH-1:0] AMP_TX_RD;
wire             RV_LFO_DATA;
wire             LFO_AMP_DATA;
wire             AMP_TX_DATA;

wire [15:0]      LFO_AMP_GAIN;


i2s_rv receiver(
    .sck(shared_sck),
    .WS(shared_WS),
    .SD(shared_SD),
    .reset(shared_reset),
    .data_ready(RV_LFO_DATA),
    .output_LD(RV_LFO_LD),
    .output_RD(RV_LFO_RD)
);

tremolo_lfo LFO(
    .data_valid(RV_LFO_DATA),
    .sck(shared_sck),
    .reset(shared_reset),
    .control_rate(shared_control_rate),
    .control_depth(shared_control_depth), 
    .in_LD(RV_LFO_LD), 
    .in_RD(RV_LFO_RD),
    .data_ready(LFO_AMP_DATA),  
    .out_LD(LFO_AMP_LD),
    .out_RD(LFO_AMP_RD),   
    .tremolo_gain(LFO_AMP_GAIN)
);

amplifier u_amplifier(
    .data_valid(LFO_AMP_DATA),
    .sck(shared_sck),
    .reset(shared_reset),
    .in_LD(LFO_AMP_LD),
    .in_RD(LFO_AMP_RD),
    .G(LFO_AMP_GAIN),
    .data_ready(AMP_TX_DATA),
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
