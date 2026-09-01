import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer
import random as pyrandom
from pathlib import Path

DSP_CLK = 20
I2S_CLK = 325.52
WIDTH = 24
SLOT_WIDTH = 32
COEFFICIENT_WIDTH = 16
FRAC_BITS = 15
NUM_TAPS = 63
LATENCY = 2

MAX_24 = (1 << (WIDTH - 1)) - 1   #  8388607
MIN_24 = -(1 << (WIDTH - 1))      # -8388608

values = []

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
    rounded = int(result) + (1 << (FRAC_BITS - 1))
    scaled = rounded >> FRAC_BITS
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
              left_accumulator += (
                  input_frames[n - k][0] * coefficients[k]
              )

              right_accumulator += (
                  input_frames[n - k][1] * coefficients[k]
              )
      
      expected_output.append(
          (processing(left_accumulator),
           processing(right_accumulator))
      )

    return expected_output

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


def format_frame(frame, index=None):
    left, right = frame
    prefix = f"[{index:03d}] " if index is not None else ""
    return (
        f"{prefix}"
        f"L=0x{left & 0xFFFFFF:06X} ({two__compliment_to_int(left, WIDTH):9d})  "
        f"R=0x{right & 0xFFFFFF:06X} ({two__compliment_to_int(right, WIDTH):9d})"
    )


def format_frame_list(title, frames):
    lines = [title]
    lines.extend(format_frame(frame, i) for i, frame in enumerate(frames))
    return "\n".join(lines)
    
@cocotb.test()
async def multiple_frame(dut):

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    
    await reset(dut)
    
    input_frames = []
    for i in range(30):
        input_frames.append((i,i + 100))
    
    expected_output = fir_model(input_frames)

    await FallingEdge(dut.top_WS) # frame synchronization
    send = cocotb.start_soon(send_frames(dut, input_frames))
    receive = cocotb.start_soon(receive_frames(dut, len(input_frames) + LATENCY))

    await send
    output_frames = await receive

    actual_output = output_frames[LATENCY: len(input_frames)+LATENCY]

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
async def reset_mid_stream(dut):

    pyrandom.seed(12345)

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)
    
    await reset(dut)

    initial_frames = []
    for _ in range(30):
      left = pyrandom.randint(MIN_24, MAX_24)
      right = pyrandom.randint(MIN_24, MAX_24)
      initial_frames.append((left, right))

    second_frames = []

    for _ in range(50):
      left = pyrandom.randint(MIN_24, MAX_24)
      right = pyrandom.randint(MIN_24, MAX_24)
      second_frames.append((left, right))
    
    expected_output = fir_model(second_frames)
    await FallingEdge(dut.top_WS) 
    init_send = cocotb.start_soon(send_frames(dut, initial_frames))

    #reset in the middle of a frame
    await RisingEdge(dut.top_WS)
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
    













  



