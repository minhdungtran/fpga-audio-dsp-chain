/* ==============================================================================
 * Module:      I2S_TX
 * Description: I2S stereo audio transmitter.
 *
 *              This module serializes left and right parallel audio samples onto
 *              the I2S serial data line `SD`. Data is transmitted on the falling
 *              edge of the bit clock `sck`, with `WS` selecting the active audio
 *              channel.
 *
 *              Operation:
 *              - There is 1 WS clock delay at the start for frame synchronization
 *              - When `valid_i` is high, the module loads `ld_i` and
 *                `rd_i` into `pending_LD` and `pending_RD` accordingly.
 *                When this happens, `pending_valid` pulses high until the 
 *                pending sample is loaded into the transmit shift registers.
 *
 *              - A transition on `WS` marks the start of a new channel period.
 *
 *              - When `Prev_WS` = 1 and `WS` = 0 (the start of a new WS cycle),
 *                the module loads `pending_LD` and `pending_RD` to the `reg_LD` 
 *                and reg_RD to start the internal shifting.
 *
 *              - The selected channel sample is then shifted out MSB first on
 *                `SD` for `WIDTH` bit-clock cycles.
 *
 *              Reset behavior:
 *              - When `reset` is asserted, all internal registers, counters, and
 *                the serial data output are cleared.
 * ==============================================================================
 */



module i2s_tx
#(
    parameter WIDTH = 24
)
(
    input logic                          sck,  // whenever clock tick, new bit will be waiting
    input logic                           WS,  // select the left(0) or right channel(1)
    input logic                      valid_i,  // the data is ready to go through transmitter
    input logic signed [WIDTH-1:0]      ld_i,  // the data from left channel
    input logic signed [WIDTH-1:0]      rd_i,  // the data from right channel    
    input logic                        reset,     
    
    output logic                     ready_o,
    output logic                          SD

);
localparam SAMPLE_WIDTH = $clog2(24);

logic                    frame_sync;
logic                    pending_valid;
logic                    shift_enable; // allow bit to start coming in channel
logic                    Prev_WS;      // to signal when we change the channel that receive SD
logic [SAMPLE_WIDTH:0]   bit_counter;  // to count when we reach 24 bit for a channel
assign ready_o = !pending_valid;


logic                          reg_SD;
logic signed [WIDTH-1:0]   pending_LD;
logic signed [WIDTH-1:0]   pending_RD;
logic        [WIDTH-1:0]       reg_LD;
logic        [WIDTH-1:0]       reg_RD;

assign SD = reg_SD;

always_ff @(negedge sck) begin

    //not reset mean we are in middle of the stream
    if (reset) begin   
        shift_enable  <= 0;
        Prev_WS       <= WS;
        bit_counter   <= 0;
        reg_LD        <= 0;
        reg_RD        <= 0;
        reg_SD        <= 0;
        pending_LD    <= 0;
        pending_RD    <= 0;
        pending_valid <= 0;
        frame_sync    <= 0;
    end else begin
      if ((Prev_WS == 1'b1) && (WS == 1'b0)) begin
        frame_sync <= 1;
      end 

      if (valid_i & ready_o) begin
        pending_LD <= ld_i;
        pending_RD <= rd_i;
        pending_valid <= 1'b1;
      end
      //Detect change in receiving channel: wait 1 cycle 
      if ((Prev_WS != WS) & frame_sync) begin
        shift_enable <= 1;
        bit_counter <= 0;

        if ((Prev_WS == 1'b1) && (WS == 1'b0) && pending_valid) begin
          reg_LD <= pending_LD;
          reg_RD <= pending_RD;
          pending_valid <= 1'b0;
        end 
      end
        //Data shifting
      else if (shift_enable) begin 
        if (WS == 0) begin
            reg_SD <= reg_LD[WIDTH-1];
            reg_LD <= {reg_LD[WIDTH-2:0],1'b0};      
        end else begin
            reg_SD <= reg_RD[WIDTH-1];
            reg_RD <= {reg_RD[WIDTH-2:0],1'b0};   
        end  
    
          //Check if we are on the final bit
        if (bit_counter == WIDTH-1) begin
            shift_enable <= 0;

          //If not reach final bit yet, continue shifting
        end else begin
          bit_counter <= bit_counter + 1;
        end 
      end    
      Prev_WS <= WS;
    end  
end  
endmodule
