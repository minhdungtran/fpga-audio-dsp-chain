import cocotb
import random
import math
import numpy as np
from pathlib import Path
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, with_timeout


DSP_CLK = 20
I2S_CLK = 325.52
WIDTH = 24
SLOT_WIDTH = 32
FIR_FRAC_BITS = 15
AMP_FRAC_BITS = 14

NUM_TAPS = 63
LATENCY = 3

ON = 1
OFF = 0

MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608

TEST_DIR = Path(__file__).resolve().parent
PROJECT_DIR = TEST_DIR.parents[2]

file_path = (
    PROJECT_DIR
    / "coefficients"
    / "fir_8khz_63tap_q15.mem"
)

if not file_path.is_file():
    raise FileNotFoundError(
        f"Coefficient file not found: {file_path}"
    )

with file_path.open("r") as f:
    hex_values = [
        line.strip()
        for line in f
        if line.strip() and not line.strip().startswith("//")
    ]

coefficients_int16 = np.array(
    [int(value, 16) for value in hex_values],
    dtype=np.uint16
).view(np.int16)

coefficients_q15 = coefficients_int16.astype(np.float64) / 32768.0

coefficients = [
    int(value)
    for value in coefficients_int16
]

async def reset(dut):
    await FallingEdge(dut.top_i2s_clk)
    dut.top_i2s_reset.value = 1
    await FallingEdge(dut.top_dsp_clk)
    dut.top_dsp_reset.value = 1

    for _ in range (10): 
        await RisingEdge(dut.top_i2s_clk)

    dut.top_i2s_reset.value = 0
    dut.top_dsp_reset.value = 0

    await RisingEdge(dut.top_i2s_clk)

async def generated_WS(dut):

    while True:
        dut.top_WS.value = 1
        for _ in range(SLOT_WIDTH):
            await FallingEdge(dut.top_i2s_clk)

        dut.top_WS.value = 0
        for _ in range(SLOT_WIDTH):
            await FallingEdge(dut.top_i2s_clk)

async def clock_start(dut, dsp_period, i2s_period):
  
  cocotb.start_soon(Clock(dut.top_dsp_clk, dsp_period, unit="ns").start())

  cocotb.start_soon(Clock(dut.top_i2s_clk, i2s_period, unit="ns").start())

  cocotb.start_soon(generated_WS(dut))

def sat_clip(value, width=24):
    if value > MAX_24:
        return MAX_24
    if value < MIN_24:
        return MIN_24
    return value

def processing(result):
    rounded = int(result) + (1 << (FIR_FRAC_BITS - 1))
    scaled = rounded >> FIR_FRAC_BITS
    return sat_clip(scaled, WIDTH)

def two__compliment_to_int(sample, width):
    sample &= ((1<<width) - 1)
    # check signed bit
    if sample & (1 << (width-1) ):
        sample = sample - (1<<width)
    return sample

def int_to_two_compliment(value, width):
    return value & (((1 << width) - 1))

def fir_model(input_frames):

    expected_output = []

    for n in range(len(input_frames)): 
      left_accumulator = 0
      right_accumulator = 0

      for k in range(NUM_TAPS):
          if n - k >= 0:
              left_sample = two__compliment_to_int(input_frames[n - k][0], WIDTH)
              right_sample = two__compliment_to_int(input_frames[n - k][1], WIDTH)

              left_accumulator += (left_sample * coefficients[k])
              right_accumulator += (right_sample * coefficients[k])
      
      expected_output.append(
          (processing(left_accumulator),
           processing(right_accumulator))
      )

    return expected_output

def unsigned_amp_model(sample, gain, frac_bits= AMP_FRAC_BITS, width= WIDTH):
    return sat_clip((sample*gain) >> frac_bits, width) 

def signed_amp_model(sample, gain):
    return int_to_two_compliment(
        unsigned_amp_model(two__compliment_to_int(sample, WIDTH), gain, AMP_FRAC_BITS, WIDTH), WIDTH)

def amp_config(dut, gain):
    dut.gain_value.value = gain

def tremolo_config(dut, control_rate, control_depth):
    dut.control_rate.value = control_rate
    dut.control_depth.value = control_depth 

def lfo_rom_value(address):
   to_rad = address*2*math.pi/256
   uni_polar = (math.sin(to_rad)+1)/2
   u014 = round(((1<<14)) * uni_polar)

   if u014 == 16384: 
      u014 = 16383
   return u014

def next_accumulator(current, control_rate):
    return (current + int(control_rate)) & 0xFFFF

def expected_gain(gain, address):
   mask = (1<<16) - 1
   G = (1<<14)- ((gain*int(lfo_rom_value(address)))>>14)
   return G & mask

def tremolo_model(input_frames, expected_accumulator, control_rate, control_depth):
    output_frames = []
    for frame in input_frames:
      current = (expected_accumulator >> 8) & 0xFF
      expected_accumulator = next_accumulator(expected_accumulator, control_rate)
      gain = expected_gain(control_depth, current)
      output_frame = tuple(signed_amp_model(sample, gain) for sample in frame)
      output_frames.append(output_frame)
    return output_frames

def dsp_model(input_frames,
              amp_gain,
              expected_accumulator, control_rate, control_depth, amp_en, fir_en, trem_en):

    if amp_en:   
      first_change = [
          tuple(signed_amp_model(sample, amp_gain) for sample in frame) 
          for frame in input_frames]
    else: 
      first_change = input_frames


    if fir_en:
      second_change = fir_model(first_change)
    else: 
      second_change = first_change


    if trem_en:
      third_change = tremolo_model(second_change, expected_accumulator, control_rate, control_depth)
    else: 
      third_change = second_change

    return [(two__compliment_to_int(l, WIDTH), two__compliment_to_int(r, WIDTH)) for l, r in third_change]


async def send_i2s_word(dut, audio, width = WIDTH): 

    await RisingEdge(dut.top_i2s_clk) # 1 clock delay

    for i in range(width-1,-1,-1):
        await FallingEdge(dut.top_i2s_clk)
        bit = (audio >> i) & 1
        dut.top_in_SD.value = bit

async def send_i2s_frame(dut, left_audio, right_audio):
    await FallingEdge(dut.top_WS)
    await send_i2s_word(dut, left_audio, WIDTH)
    await RisingEdge(dut.top_WS)
    await send_i2s_word(dut, right_audio, WIDTH)

async def send_frames(dut, input_frames):
    for left, right in input_frames:
        await send_i2s_frame(dut, left, right)

async def receive_i2s_word(dut, width = WIDTH):  

    await FallingEdge(dut.top_i2s_clk) # 1 cycle delay
    await FallingEdge(dut.top_i2s_clk)

    output = 0

    for i in range(width-1,-1,-1):
        await RisingEdge(dut.top_i2s_clk)
        bit = int(dut.top_out_SD.value)
        output = output | (bit << i)
        
    return output

async def receive_i2s_frame(dut):
    await FallingEdge(dut.top_WS)
    left = await receive_i2s_word(dut, WIDTH)
    await RisingEdge(dut.top_WS)
    right = await receive_i2s_word(dut, WIDTH)
    return (two__compliment_to_int(left, WIDTH),
            two__compliment_to_int(right, WIDTH)
    )

async def receive_frames(dut, nbr_of_frames):
    output_frames = []

    for _ in range (nbr_of_frames):
        left_out, right_out = await receive_i2s_frame(dut)
        output_frames.append((left_out, right_out))

    return output_frames

def dsp_config(dut, amp_en, fir_en, trem_en):
    dut.amp_en.value = amp_en
    dut.fir_en.value = fir_en
    dut.trem_en.value = trem_en

async def run_dsp_chain_test(dut, amp_gain, control_rate, control_depth, expected_accumulator, amp_en, fir_en, trem_en, nbr_of_frames):

    await clock_start(dut, DSP_CLK, I2S_CLK) 
    dsp_config(dut, amp_en, fir_en, trem_en)
    tremolo_config(dut, control_rate, control_depth)
    amp_config(dut, amp_gain)

    await reset(dut)

    random.seed(1)
    input_frames = []
    for _ in range(nbr_of_frames):
        left = random.getrandbits(WIDTH)
        right = random.getrandbits(WIDTH)
        input_frames.append((left,right))

    await FallingEdge(dut.top_WS) # frame synchronization
    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames)+3))

    await send
    output_frames = await receive
    expected_frames = dsp_model(input_frames, amp_gain, expected_accumulator, control_rate, control_depth, amp_en, fir_en ,trem_en)

    actual_frames = output_frames[LATENCY: len(input_frames)+LATENCY]


    for index, (expected_frame, actual_frame) in enumerate(
        zip(expected_frames, actual_frames)
    ):
        assert expected_frames == actual_frames, (
          f"First mismatch at frame: {index}\n"
          f"Received: {expected_frame}. Expected: {actual_frame}"
        )

@cocotb.test()
async def all_on(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= ON, fir_en=ON, trem_en=ON)
@cocotb.test()
async def amp_on_only(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= ON, fir_en=OFF, trem_en=OFF)

@cocotb.test()
async def fir_on_only(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= OFF, fir_en=ON, trem_en=OFF)

@cocotb.test()
async def trem_on_only(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= OFF, fir_en=OFF, trem_en=ON)

@cocotb.test()
async def all_off(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= OFF, fir_en=OFF, trem_en=OFF)

@cocotb.test()
async def amp_fir_on(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= ON, fir_en=ON, trem_en=OFF)

@cocotb.test()
async def amp_trem_on(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= ON, fir_en=OFF, trem_en= ON)

@cocotb.test()
async def fir_trem_on(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 30,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= OFF, fir_en=ON, trem_en= ON)

@cocotb.test()
async def long_run(dut):
    await run_dsp_chain_test(dut,
                            nbr_of_frames= 500,
                            amp_gain=100,
                            expected_accumulator=0, control_rate=7, control_depth=8192, 
                            amp_en= ON, fir_en=ON, trem_en=ON)

@cocotb.test()
async def reset_mid_stream(dut):

    random.seed(1)
    control_rate = 7
    control_depth = 8192
    amp_gain = 100
    amp_en, fir_en, trem_en = ON, OFF, OFF
    dsp_config(dut, amp_en, fir_en, trem_en)
    tremolo_config(dut, control_rate, control_depth)
    amp_config(dut, amp_gain)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    await reset(dut)

    initial_frames = []
    for _ in range(30):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      initial_frames.append((left, right))

    second_frames = []

    for _ in range(50):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      second_frames.append((left, right))
    
    expected_output = dsp_model(second_frames, amp_gain, 0, control_rate, control_depth, amp_en, fir_en, trem_en)
    await FallingEdge(dut.top_WS) 
    init_send = cocotb.start_soon(send_frames(dut, initial_frames))

    #reset in the middle of a frame
    await FallingEdge(dut.top_WS)

    for _ in range(12): 
        await FallingEdge(dut.top_i2s_clk)

    await reset(dut)
    init_send.cancel()
    
    await FallingEdge(dut.top_WS)
    send = cocotb.start_soon(send_frames(dut, second_frames))
    receive = cocotb.start_soon(receive_frames(dut, len(second_frames) + LATENCY))

    await send
    output_frames = await receive

    actual_output = output_frames[LATENCY: len(second_frames)+LATENCY]

    for index, (expected_frame, actual_frame) in enumerate(
        zip(expected_output, actual_output)
    ):
        assert expected_frame == actual_frame, (
          f"First mismatch at frame: {index}\n"
          f"Received: {actual_frame}. Expected: {expected_frame}"
        )

    assert len(expected_output) == len(actual_output), (
      f"Frame count mismatch: received {len(actual_output)}, "
      f"expected {len(expected_output)}"
    )

@cocotb.test()
async def change_config_mid_stream(dut):

    random.seed(1)
    control_rate = 7
    control_depth = 8192
    amp_gain = 100
    amp_en, fir_en, trem_en = ON, OFF, ON
    tremolo_config(dut, control_rate, control_depth)
    dsp_config(dut, amp_en, fir_en, trem_en)
    amp_config(dut, amp_gain)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    await reset(dut)

    initial_frames = []
    for _ in range(50):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      initial_frames.append((left, right))

    second_frames = []

    for _ in range(50):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      second_frames.append((left, right))
    
    await FallingEdge(dut.top_WS) 
    init_send = cocotb.start_soon(send_frames(dut, initial_frames))
    receive1 = cocotb.start_soon(receive_frames(dut, len(initial_frames) + LATENCY))

    await init_send
    output_frames1 = await receive1

    actual_output1 = output_frames1[LATENCY: len(initial_frames)+LATENCY]
    expected_output1 = dsp_model(initial_frames, amp_gain, 0, control_rate, control_depth, amp_en, fir_en, trem_en)

    assert expected_output1 == actual_output1, (
        f"Mismatch in the first configuration's output frames\n"
        f"Received: {actual_output1}. Expected: {expected_output1}"
    )

    #change dsp configuration in the middle of a frame
    await RisingEdge(dut.top_WS)
    amp_en2, fir_en2, trem_en2 = OFF, ON, ON
    dsp_config(dut, amp_en2, fir_en2, trem_en2)
    await reset(dut)
    
    await FallingEdge(dut.top_WS)
    send = cocotb.start_soon(send_frames(dut, second_frames))
    receive2 = cocotb.start_soon(receive_frames(dut, len(second_frames) + LATENCY))

    await send
    output_frames2 = await receive2
    expected_output2 = dsp_model(second_frames, amp_gain, 0, control_rate, control_depth, amp_en2, fir_en2, trem_en2)

    actual_output2 = output_frames2[LATENCY: len(second_frames)+LATENCY]

    assert expected_output2 == actual_output2, (
        f"Mismatch in the second configuration's output frames\n"
        f"Received: {actual_output2}. Expected: {expected_output2}"
    )

@cocotb.test()
async def change_amp_mid_stream(dut):

    random.seed(1)
    control_rate = 7
    control_depth = 8192
    amp_gain1 = 100
    amp_en = ON
    fir_en = OFF
    trem_en = ON
    dsp_config(dut, amp_en, fir_en, trem_en)
    tremolo_config(dut, control_rate, control_depth)
    amp_config(dut, amp_gain1)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    await reset(dut)

    initial_frames = []
    for _ in range(30):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      initial_frames.append((left, right))

    second_frames = []

    for _ in range(30):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      second_frames.append((left, right))
    
    await FallingEdge(dut.top_WS) 
    init_send = cocotb.start_soon(send_frames(dut, initial_frames))
    receive1 = cocotb.start_soon(receive_frames(dut, len(initial_frames) + LATENCY))

    await init_send
    output_frames1 = await receive1

    actual_output1 = output_frames1[LATENCY: len(initial_frames)+LATENCY]
    expected_output1 = dsp_model(initial_frames, amp_gain1, 0, control_rate, control_depth, amp_en, fir_en, trem_en)

    assert expected_output1 == actual_output1, (
        f"Mismatch in the first configuration's output frames\n"
        f"Received: {actual_output1}. Expected: {expected_output1}"
    )

    #change dsp configuration in the middle of a frame
    await RisingEdge(dut.top_WS)
    amp_gain2 = 8192
    amp_config(dut, amp_gain2)
    await reset(dut)
    
    await FallingEdge(dut.top_WS)
    send = cocotb.start_soon(send_frames(dut, second_frames))
    receive2 = cocotb.start_soon(receive_frames(dut, len(second_frames) + LATENCY))

    await send
    output_frames2 = await receive2
    expected_output2 = dsp_model(second_frames, amp_gain2, 0, control_rate, control_depth, amp_en, fir_en, trem_en)

    actual_output2 = output_frames2[LATENCY: len(second_frames)+LATENCY]

    assert expected_output2 == actual_output2, (
        f"Mismatch in the second configuration's output frames\n"
        f"Received: {actual_output2}. Expected: {expected_output2}"
    )

@cocotb.test()
async def change_trem_mid_stream(dut):

    random.seed(1)
    control_rate1 = 7
    control_depth1 = 8192
    amp_gain = 100
    amp_en, fir_en, trem_en = ON, OFF, ON
    tremolo_config(dut, control_rate1, control_depth1)
    dsp_config(dut, amp_en, fir_en, trem_en)
    amp_config(dut, amp_gain)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    await reset(dut)

    initial_frames = []
    for _ in range(20):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      initial_frames.append((left, right))

    second_frames = []

    for _ in range(20):
      left = random.getrandbits(WIDTH)
      right = random.getrandbits(WIDTH)
      second_frames.append((left, right))
    
    await FallingEdge(dut.top_WS) 
    init_send = cocotb.start_soon(send_frames(dut, initial_frames))
    receive1 = cocotb.start_soon(receive_frames(dut, len(initial_frames) + LATENCY))

    await init_send
    output_frames1 = await receive1

    actual_output1 = output_frames1[LATENCY: len(initial_frames)+LATENCY]
    expected_output1 = dsp_model(initial_frames, amp_gain, 0, control_rate1, control_depth1, amp_en, fir_en, trem_en)

    assert expected_output1 == actual_output1, (
        f"Mismatch in the first configuration's output frames\n"
        f"Received: {actual_output1}. Expected: {expected_output1}"
    )

    #change dsp configuration in the middle of a frame
    await RisingEdge(dut.top_WS)
    control_rate2 = 10
    control_depth2 = 300
    tremolo_config(dut, control_rate2, control_depth2)
    await reset(dut)
    
    await FallingEdge(dut.top_WS)
    send = cocotb.start_soon(send_frames(dut, second_frames))
    receive2 = cocotb.start_soon(receive_frames(dut, len(second_frames) + LATENCY))

    await send
    output_frames2 = await receive2
    expected_output2 = dsp_model(second_frames, amp_gain, 0, control_rate2, control_depth2, amp_en, fir_en, trem_en)

    actual_output2 = output_frames2[LATENCY: len(second_frames)+LATENCY]

    assert expected_output2 == actual_output2, (
        f"Mismatch in the second configuration's output frames\n"
        f"Received: {actual_output2}. Expected: {expected_output2}"
    )

@cocotb.test()
async def full_dynamic_range_saturation_test(dut):
    control_rate, control_depth = 7, 8192
    amp_gain = 32767  
    amp_en, fir_en, trem_en = ON, ON, OFF

    await clock_start(dut, DSP_CLK, I2S_CLK)

    dsp_config(dut, amp_en, fir_en, trem_en)
    tremolo_config(dut, control_rate, control_depth)
    amp_config(dut, amp_gain)
    await reset(dut)

    MIN_24_BIT = 1 << (WIDTH-1)

    test_streams = {
        "Full Scale Positive": [(MAX_24, MAX_24) for _ in range(10)],
        "Full Scale Negative": [(MIN_24_BIT, MIN_24_BIT) for _ in range(10)],
        "Alternating Impulse": [
            (MAX_24, MIN_24_BIT) if i % 2 == 0 else (MIN_24_BIT, MAX_24)
            for i in range(10)
        ],
    }

    for stream_name, frames in test_streams.items():
        dsp_config(dut, amp_en, fir_en, trem_en)
        tremolo_config(dut, control_rate, control_depth)
        amp_config(dut, amp_gain)
        await reset(dut)

        await FallingEdge(dut.top_WS)
        send = cocotb.start_soon(send_frames(dut, frames))
        receive = cocotb.start_soon(receive_frames(dut, len(frames) + LATENCY))

        await send
        out_frames = await receive

        actual = out_frames[LATENCY : len(frames) + LATENCY]
        expected = dsp_model(frames, amp_gain, 0, control_rate, control_depth, amp_en, fir_en, trem_en)

        assert actual == expected, (
            f"Saturation failure in '{stream_name}':\n"
            f"Received: {actual}\nExpected: {expected}"
        )

   