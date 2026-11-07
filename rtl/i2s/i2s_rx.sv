/* ==============================================================================
 * Module:      i2s_rx
 * Description: Standard I2S receiver for one stereo audio frame.
 *
 *              This module receives serial I2S audio data using the rising edge
 *              of the bit clock `sck`.
 *
 *              Protocol behavior:
 *              - A change in `WS` marks the start of a new channel slot.
 *              - There is 1 WS clock delay at the start for frame synchronization
 *              - Following standard I2S timing, the first `sck` rising edge after
 *                a `WS` transition is treated as the one-bit delay period.
 *              - After this delay, the module shifts in `WIDTH` serial bits from
 *                `SD`, MSB first.
 *
 *              Output behavior:
 *              - Received channel data is first stored in internal shift registers.
 *              - After both left and right channels have been received, the samples
 *                are copied into `ld_o` and `rd_o`.
 *              - `data_ready` pulses high for one `sck` cycle to indicate that
 *                `ld_o` and `rd_o` contain a complete stereo frame.
 *              - `ld_o` and `rd_o` remain stable until the next complete
 *                stereo frame is received.
 *
 *              Notes:
 *              - This receiver assumes valid standard I2S timing, where the MSB
 *                appears one bit-clock after a `WS` transition.
 * ==============================================================================
 */



module i2s_rx
#(
    parameter WIDTH = 24
)
(
    input logic                     sck,       // I2S bit clock; SD is sampled on rising edge
    input logic                     WS,        // select the left(0) or right channel(1)
    input logic                     SD,        // the serial data that will come in
    input logic                     reset,     

    output logic                    valid_o, //when the data fully assembled for the next process
    output logic signed [WIDTH-1:0] ld_o,
    output logic signed [WIDTH-1:0] rd_o
);

localparam SAMPLE_WIDTH = $clog2(24);

logic                    frame_sync;
logic                    l_done;       // high if the left data is fully assembled
logic                    r_done;       // high if the right data is fully assembled
logic                    shift_enable; // enables shifting after the I2S one-bit delay
logic                    Prev_WS;      // to signal when we change the channel that receive SD
logic [SAMPLE_WIDTH:0]   bit_counter;  // to count when we reach 24 bit for a channel

logic                   o_valid_r;
logic        [WIDTH-1:0]   reg_LD;
logic        [WIDTH-1:0]   reg_RD;
logic signed [WIDTH-1:0]   final_LD;
logic signed [WIDTH-1:0]   final_RD;

assign valid_o = o_valid_r;
assign ld_o = final_LD;
assign rd_o = final_RD;

always_ff @(posedge sck) begin

    //not reset mean we are in middle of the stream
    if (reset) begin   
        l_done        <= 0;
        r_done        <= 0;
        shift_enable  <= 0;
        Prev_WS       <= WS;
        bit_counter   <= 0;
        o_valid_r <= 0;
        reg_LD        <= 0;
        reg_RD        <= 0;
        final_LD      <= 0;
        final_RD      <= 0;
        frame_sync          <= 0;
    end else begin

      o_valid_r   <= 0;   
      
      if ((Prev_WS == 1'b0) & (WS == 1'b1)) begin
        frame_sync <= 1'b1;
      end
      
      //Detect change in receiving channel: wait 1 cycle 
      //Discard the incomplete frame
      if ((Prev_WS != WS) & frame_sync) begin
          shift_enable <= 1;
          bit_counter <= 0;
        //If WS suddenly change when shift_enable is on
          if (shift_enable) begin
            reg_LD <= 0;
            reg_RD <= 0;
            l_done <= 0;
            r_done <= 0;
          end 
      end
    
      //Data shifting
      if (shift_enable) begin 
        if (WS == 0) begin
            reg_LD <=  { reg_LD[WIDTH -2 :0], SD};       
        end else begin
            reg_RD <=  { reg_RD[WIDTH -2 :0], SD};
        end  
    
        //Check if we are on the final bit
        if (bit_counter == WIDTH-1) begin
          shift_enable <= 0;
        
          if (WS == 0) begin 
              l_done <= 1;
          end else begin 
              r_done <= 1;
          end 
        //If not reach final bit yet, continue shifting
        end else begin
          bit_counter <= bit_counter + 1;
        end 
      end 
    
      Prev_WS <= WS;

      if (l_done && r_done) begin 
        final_RD <= reg_RD;
        final_LD <= reg_LD;
        o_valid_r <= 1;

        l_done <= 0;
        r_done <= 0;
      end 
  end  
end
endmodule
