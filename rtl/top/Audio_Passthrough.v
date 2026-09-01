
module Audio_Passthrough
#(
    parameter WIDTH = 24
)
(
    input wire              shared_sck,       
    input wire              shared_WS,        
    input wire              shared_SD,        
    input wire              shared_reset,    

    output wire             output_SD
       
);

wire             data_ready;
wire [WIDTH-1:0] wire_LD;
wire [WIDTH-1:0] wire_RD;

i2s_rv receiver(
    .sck(shared_sck),
    .WS(shared_WS),
    .SD(shared_SD),
    .reset(shared_reset),
    .data_ready(data_ready),
    .output_LD(wire_LD),
    .output_RD(wire_RD)
);

i2s_tx transmitter(
    .sck(shared_sck),
    .WS(shared_WS),
    .data_valid(data_ready),
    .input_LD(wire_LD),
    .input_RD(wire_RD),
    .reset(shared_reset),
    .SD(output_SD)
);
endmodule