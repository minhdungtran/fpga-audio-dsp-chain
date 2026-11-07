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

- Feedback (`fb_i`): Determines how much of the delayed sample is written back into the circular buffer. Configuration from 0 to 1 in unsigned U0.14 fixed-point format.

- Wet/dry mix (`w_i`): Controls the balance between the original (dry) and delayed (wet) signals. Configuration from 0 to 1 in unsigned U0.14 fixed-point format.

- Delay time (`delay_i`): Sets the interval between the original signal and its echoes, in milliseconds. Valid range: 0 to 500 ms. Zero delay is treated as bypass.

**Parameter**

- `FRAC_BITS` for U0.14
- `SAMPLE_F` represents the current sampling frequency in Hz
- `MAX_DELAY_MS`: the maximum delay allowed. This is used to create the maximum circular buffer size for the delay

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
- For integration, the chain only starts when delay finishes clearing its brams.

## Reverb

**Additional configuration and parameters:**

```systemverilog
    parameter FRAC_BITS = 14,
    parameter MAX_DECAY = 50,

    input logic                       bypass,       // Enables/disables reverb
    input logic [1:0]                 room_i,       // Configurable room size
    input logic [5:0]                 decay_60,     // RT60 decay time
    input logic [FRAC_BITS-1:0]       w_i,          // Wet/dry mix
    input logic [FRAC_BITS-1:0]       diffusion_i   // All-pass diffusion coefficient
```
### Schroeder reverb

- The reverb module is implemented accordingly to Schroeder architecture
- Architecture:
  input -> 4 Comb filter -> all-pass filter -> all-pass filter -> output

### Configuration

- **Decay (RT60):** Time required for the reverb amplitude to decrease by 60 dB. Controls the comb filters' feedback coefficients.

- **Room size:** Controls reflection spacing by scaling the comb filters' delay lengths. Three modes: Small, Medium, Large.

- **Diffusion:** Controls how smoothly reflections blend by adjusting the all-pass filters' coefficients.

- **Wet mix:** Controls the proportion of dry and reverberated signals at the final output.

- **Bypass:** Enables/disables the reverb effect

### Comb filter

Similar to the delay module, but uses shorter delay lengths to generate closely spaced reflections. Each comb filter outputs its delayed signal without an individual wet/dry mixer. Four comb filters combined together to create a complicated pattern of echoes.

**Mathematics:**

The configurations used in comb filter includes: Room size, Decay

$$
\begin{aligned}
r_i[n] &= v_i[n-D_i] = RAM_i[ptr_i] \\
v_i[n] &= x[n] + g_i r_i[n] \\
y_i[n] &= r_i[n]
\end{aligned}
$$

**Feedback coefficient:**

$$
g_i = 10^{-\frac{3D_i}{f_s T_{60}}}
$$

**Room-size configuration:**

$$
D_i = \operatorname{round}(sD_{i,\text{base}})
$$

Where:

- $D_i$: Active comb delay in samples. This is fixed in each comb filter.
- $f_s$: Sampling frequency (48 kHz).
- $T_{60}$: Configured decay time in seconds. The range is from 0 to 5s.
- $s$: Room-size scaling factor. Small is 0.75, Medium is 1 and Large is 1.25
- $g_i$: Comb feedback coefficient.

**Base Delay Lengths (48 kHz):**

| Delay (ms) | Delay (samples) |
| --- | --- |
| 29.7 | 1,426 |
| 37.1 | 1,781 |
| 41.1 | 1,973 |
| 43.7 | 2,098 |

The delay lengths are converted from milliseconds into samples:

$$
D_{i,\text{base}} =
\operatorname{round}\left(\frac{D_{i,\text{ms}}f_s}{1000}\right)
$$

### All pass filter

The all-pass filters are used to increase the diffusion of the reverberated signal by spreading reflections across time, producing a smoother and denser reverb tail.

Unlike the comb filter, an ideal all-pass filter has a flat magnitude frequency response. It changes the phase of different frequency components without changing their magnitudes.

The two all-pass filters are connected in series to progressively increase reflection density.

**Mathmatic**

$$
\begin{aligned}
r[n-D] &\leftarrow RAM[ptr] \\
r[n] &= x[n] + a \cdot r[n-D] \\
y[n] &= r[n-D] - a \cdot r[n]
\end{aligned}
$$

**Configuration**

- **Diffusion:** how chaotic the echoes is. Range from 0 to 1, written in `U0.14`

**Delay**

For the delay, we used a fixed 5 ms and 1.71 ms accordingly for all-pass filter 1 and 2.

| Delay (ms) | Delay (samples) |
| --- | --- |
| 5 | 249 |
| 1.71 | 82 |


## Amplifier

Stereo fixed-point audio amplifier used to adjust the amplitude of incoming PCM samples. Both channels share the same gain configuration, while their samples are processed independently.

The amplifier supports positive and negative gain values, saturation, and bypass.

**Additional configuration and parameters:**

```systemverilog
parameter GAIN_LENGTH = 16;

input logic                       bypass;
input logic [GAIN_LENGTH-1:0]     g;
```

**Configuration**

- **Gain (`g`):** Controls the amplification or attenuation of the input signal. Represented in signed Q2.14 fixed-point format, with a range from -2 to approximately +2.
  - `0`: Mute (0×).
  - `8192`: Half amplitude (0.5×).
  - `16384`: Unity gain (1×).
  - `32767`: Approximately 2× amplification.
  - `-16384`: Negative unity gain (-1×), inverting waveform polarity.
- **Bypass (`bypass`):** When enabled, the original audio samples are forwarded without amplification.

**Parameter**

- `WIDTH`: Audio sample bit width, currently 24 bits.
- `GAIN_LENGTH`: Gain coefficient width, currently 16 bits using signed Q2.14 format.

**Mathematical Model**

The real-valued gain is calculated as:

$$
g_{\text{real}} = \frac{G}{2^{14}}
$$

For each audio channel, the amplified output is:

$$
y[n] = \operatorname{sat}_{24}\left(\frac{x[n]\cdot G}{2^{14}}\right)
$$

When bypass is enabled:

$$
y[n] = x[n]
$$

**Note**

- Both channels use the same gain value.
- Gain and bypass configurations are captured during reset; runtime updates are not currently supported.


## FIR

Stereo 63-tap FIR low-pass filter implemented using circular sample buffers and a shared multiply-accumulate (MAC) datapath.

Three different coefficient sets are provided to produce Bright, Warm, and Dark sounds.

**Additional configuration and parameters:**

```systemverilog
    parameter COEFF_WIDTH = 16,
    parameter FRAC_BITS = 15,
    parameter NUM_TAPS = 63,

    input logic                  bypass,
    input logic [1:0]            mode_i
```

**Configuration**

- Filter mode (`mode_i`): Selects one of three low-pass FIR coefficient sets, producing different frequency responses and sound characteristics.
  - `2'b00` - Bright: Low-pass filter with a cutoff frequency of 10 kHz.
  - `2'b01` - Warm: Low-pass filter with a cutoff frequency of 6 kHz.
  - `2'b10` - Dark: Low-pass filter with a cutoff frequency of 3.5 kHz.
  - `2'b11` - Reserved, defaults to Warm.
- Bypass (`bypass`): Enables/disables the FIR filtering effect. When enabled, input samples are forwarded directly to the output.

**Parameter**

- `WIDTH`: Audio sample width, currently 24-bit signed PCM.
- `COEFF_WIDTH`: Coefficient bit width, currently 16 bits.
- `FRAC_BITS`: Number of fractional bits used to represent coefficients in signed Q1.15 fixed-point format.
- `NUM_TAPS`: Number of FIR filter taps, currently 63.

**Mathematical Model**

For each channel, the FIR output is calculated as:

$$
y[n] = \sum_{k=0}^{N-1} h[k]x[n-k]
$$

Where:

- $x[n-k]$: Current and previous audio samples.
- $h[k]$: FIR filter coefficient at tap $k$.
- $N$: Number of taps, currently 63.
- $y[n]$: Filtered output sample.

**Coefficient Generation**

The FIR coefficients are generated using Python's `scipy.signal.firwin()` with a Hamming window.

Three coefficient files are generated:

```text
coefficients/fir/mem/
├── fir_bright_q15.mem
├── fir_warm_q15.mem
└── fir_dark_q15.mem
```

Each file contains 63 signed 16-bit coefficients in Q1.15 fixed-point format.

The floating-point coefficients are quantized as:

$$
H[k] = \operatorname{round}(h[k]\times 2^{15})
$$

The coefficient values are adjusted to ensure unity DC gain:

$$
\sum_{k=0}^{N-1}H[k]=2^{15}
$$

The coefficients are symmetric:

$$
H[k]=H[N-1-k]
$$

This preserves the linear-phase property of the FIR filter.

**Fixed-Point Calculation**

The FIR uses a shared MAC datapath to calculate the convolution:

$$
A[n]=\sum_{k=0}^{N-1}x[n-k]H[k]
$$

The accumulated result is rounded, arithmetically shifted right by 15 bits, and saturated to the signed 24-bit audio range:

$$
y[n]=\operatorname{sat}_{24}\left(
\operatorname{round}\left(\frac{A[n]}{2^{15}}\right)
\right)
$$

**Circular Buffer and Processing**

Two separate circular sample buffers are used to store the previous 63 samples for the left and right channels.

For each accepted stereo frame:

1. The input samples are written into their respective circular buffers.
2. The left channel is processed using 63 sequential multiply-accumulate operations.
3. The accumulated result is rounded, scaled, saturated, and saved.
4. The right channel is processed using the same MAC datapath.
5. Both processed samples are presented at the output using the valid/ready handshake protocol.

The circular-buffer pointers wrap around after `NUM_TAPS` samples.

The MAC datapath is shared between the two channels, reducing the number of multipliers required.

**Note**

- Signed 24-bit audio samples and signed 16-bit Q1.15 FIR coefficients.
- Configuration values are captured during reset; runtime updates are not yet supported.
- The circular sample buffers are cleared after reset to remove previous audio history.
- For integration, the chain only starts when FIR finishes clearing its circular buffers.
- Bypass forwards the original samples without applying FIR filtering.

