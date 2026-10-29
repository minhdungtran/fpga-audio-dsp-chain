
module audio_passthrough
#(
    parameter WIDTH = 24
)
(
    input logic              shared_sck,       
    input logic              shared_WS,        
    input logic              shared_SD,        
    input logic              shared_reset,    

    output logic             output_SD
       
);

logic             data_ready;
logic [WIDTH-1:0] wire_LD;
logic [WIDTH-1:0] wire_RD;


i2s_rx receiver(
    .sck(shared_sck),
    .WS(shared_WS),
    .SD(shared_SD),
    .reset(shared_reset),
    .valid_o(data_ready),
    .ld_o(wire_LD),
    .rd_o(wire_RD)
);

i2s_tx transmitter(
    .sck(shared_sck),
    .WS(shared_WS),
    .valid_i(data_ready),
    .ld_i(wire_LD),
    .rd_i(wire_RD),
    .reset(shared_reset),
    .ready_o(),
    .SD(output_SD)
);
endmodule
