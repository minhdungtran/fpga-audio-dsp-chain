module room_lut
#(
    parameter COMB_ID = 0 
)
(
    input logic  [1:0]  room_size,
    output logic [11:0] delay_samples_nbr
);

always_comb begin
    delay_samples_nbr = 12'd1426;
    case (COMB_ID) 
        2'd0: begin
            case (room_size) 
                2'd0: delay_samples_nbr = 12'd1070; // Small
                2'd1: delay_samples_nbr = 12'd1426; // Medium
                2'd2: delay_samples_nbr = 12'd1783; // Large
                default: delay_samples_nbr = 12'd1426;
            endcase
        end
        

        2'd1: begin
            case (room_size) 
                2'd0: delay_samples_nbr = 12'd1336; // Small
                2'd1: delay_samples_nbr = 12'd1781; // Medium
                2'd2: delay_samples_nbr = 12'd2227; // Large
                default: delay_samples_nbr = 12'd1781;
            endcase
        end

        2'd2: begin
            case (room_size) 
                2'd0: delay_samples_nbr = 12'd1480; // Small
                2'd1: delay_samples_nbr = 12'd1973; // Medium
                2'd2: delay_samples_nbr = 12'd2467; // Large
                default: delay_samples_nbr = 12'd1973;
            endcase
        end

        2'd3: begin
            case (room_size) 
                2'd0: delay_samples_nbr = 12'd1574; // Small
                2'd1: delay_samples_nbr = 12'd2098; // Medium
                2'd2: delay_samples_nbr = 12'd2623; // Large
                default: delay_samples_nbr = 12'd2098;
            endcase
        end
    endcase
end
endmodule
        
