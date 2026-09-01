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
 *              - When `data_valid` is high, the module loads `input_LD` and
 *                `input_RD` into `pending_LD` and `pending_RD` accordingly.
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
    input wire                          sck,  // whenever clock tick, new bit will be waiting
    input wire                           WS,  // select the left(0) or right channel(1)
    input wire                   data_valid,  // the data is ready to go through transmitter
    input wire signed [WIDTH-1:0]  input_LD,  // the data from left channel
    input wire signed [WIDTH-1:0]  input_RD,  // the data from right channel    
    input wire                        reset,     
     
    output wire                          SD

);
reg         frame_sync;
reg         pending_valid;
reg         shift_enable; // allow bit to start coming in channel
reg         Prev_WS;      // to signal when we change the channel that receive SD
reg [5:0]   bit_counter;  // to count when we reach 24 bit for a channel

reg                          reg_SD;
reg signed [WIDTH-1:0]   pending_LD;
reg signed [WIDTH-1:0]   pending_RD;
reg        [WIDTH-1:0]   reg_LD;
reg        [WIDTH-1:0]   reg_RD;

assign SD = reg_SD;

always @(negedge sck) begin

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

      if (data_valid) begin
        pending_LD <= input_LD;
        pending_RD <= input_RD;
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