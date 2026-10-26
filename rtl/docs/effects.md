# EFFECT DESCRIPTION

Description of currently provided DSP effects

## RTL Structure
The general structure of most effects. Depends on the effect module, certain configurations and parameters will be added.
All modules will follow the valid/ready handshake protocol.

```systemverilog
module delay
#(
    parameter WIDTH = 24
)
(   
    // Configuration, clock
    input logic                                  sck,        
    input logic                                reset,
    input logic                        configuration,       // Some configuration for the effects

    // Input interface
    input logic                              valid_i,       // Pulse high when previous modules have available samples
    output logic                             ready_o,       // Pulse high when data can be sent to this component
    input logic signed  [WIDTH-1:0]             ld_i,       // Left channel data flow in 
    input logic signed  [WIDTH-1:0]             rd_i,       // Right channel data flow in 

    // Output interface
    output logic                              valid_o,      // Pulse high when both LR and LD can be sent
    input logic                               ready_i,      // Pulse high when the next module can receive samples 
    output logic signed [WIDTH-1:0]              ld_o,      // Left channel output 
    output logic signed [WIDTH-1:0]              rd_o       // Right channel output
);
```
## Delay 
Stereo feedback-delay effect implemented using circular sample buffers. Each channel maintains its own audio history, while delay time, feedback, and wet/dry mix are shared between channels.

Addition configuration and parameters: 

```systemverilog
    parameter FRAC_BITS = 14,
    parameter SAMPLE_F = 48000,
    parameter MAX_DELAY_MS = 500  
    input logic         [FRAC_BITS-1:0]    fb_i,      // Configurable feedback value 
    input logic         [FRAC_BITS-1:0]     w_i,      // Configurable wet dry value 
    input logic         [9:0]           delay_i,      // Configurable delay time in ms, based on sample frequency
```
**Configuration**
- Feedback (fb_i): Determines how much of the delayed sample is written back into the circular buffer. Configuration from 0 to 1 in unsigned U0.14 fixed-point format.

- Wet/dry mix (w_i): Controls the balance between the original (dry) and delayed (wet) signals. Configuration from 0 to 1 in unsigned U0.14 fixed-point format.

- Delay time (delay_i): Sets the interval between the original signal and its echoes, in milliseconds. Valid range: 0 to 500 ms. Zero delay is treated as bypass.

**Parameter**
- FRAC_BITS for U0.14
- SAMPLE_F represents the current sampling frequency in Hz
- MAX_DELAY_MS: the maximum delay allowed. This is used to create the maximum circular buffer size for the delay

**Mathematical Model**

For each channel, the delay is calculated as:

$$
r[n] = \mathrm{memory}[ptr]
$$

$$
\mathrm{memory}[ptr] \leftarrow \mathrm{sat}(x[n] + g \cdot r[n])
$$

$$
y[n] = \mathrm{sat}((1-w)x[n] + w \cdot r[n])
$$
The active buffer length in samples is:

$$
D = \frac{\mathrm{delay_i}\times\mathrm{SAMPLE_F}}{1000}
$$

The circular-buffer pointer advances once per accepted audio frame and wraps around after $D$ samples.

**Note**
- Signed fixed-point multiplication, scaling and saturation.
- Configuration values are currently captured during reset; runtime updates are not yet supported.
- Delay time of 0 ms is treated as bypass.