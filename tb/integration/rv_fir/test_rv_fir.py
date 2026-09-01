import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, with_timeout
from pathlib import Path

DSP_CLK = 20
I2S_CLK = 325.52
WIDTH = 24
SLOT_WIDTH = 32
COEFFICIENT_WIDTH = 16
FRAC_BITS = 15
NUM_TAPS = 63

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
        dut.top_SD.value = bit

async def send_i2s_frame(dut, left_audio, right_audio):
    await FallingEdge(dut.top_WS)
    await send_i2s_word(dut, left_audio, WIDTH)
    await RisingEdge(dut.top_WS)
    await send_i2s_word(dut, right_audio, WIDTH)

async def send_frames(dut, input_frames):
    await FallingEdge(dut.top_WS)
    for left, right in input_frames:
        await send_i2s_frame(dut, left, right)

async def receive_fir_output(dut, nbr_of_frame):
    output_frames = []
    while len(output_frames) < nbr_of_frame:
      await RisingEdge(dut.top_dsp_clk)
      if dut.top_data_ready.value:
            left_raw = int(dut.top_out_LD.value)
            right_raw = int(dut.top_out_RD.value)

            left = two__compliment_to_int(left_raw, WIDTH)
            right = two__compliment_to_int(right_raw, WIDTH)

            output_frames.append((left, right))
    return output_frames

@cocotb.test()
async def one_frame(dut):

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)

    await reset(dut)

    input_frames = [(1, -1)]

    receive_task = cocotb.start_soon(receive_fir_output(dut, len(input_frames)))
    send_task = cocotb.start_soon(send_frames(dut, input_frames))

    actual_output = await with_timeout(receive_task, 5, "ms")
    await send_task


    expected_output = fir_model(input_frames)

    assert expected_output == actual_output,(
        f"Output Mismatch:\n"
        f"Received: {actual_output}. Expected: {expected_output}"
    )

@cocotb.test()
async def corner_case(dut):

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)

    await reset(dut)

    input_frames = [
      (0, 0),
      (1, -1),
      (123456, -123456),
      (MAX_24, MIN_24),
      (MIN_24, MAX_24),
    ]
    
    receive_task = cocotb.start_soon(receive_fir_output(dut, len(input_frames)))
    send_task = cocotb.start_soon(send_frames(dut, input_frames))

    await send_task
    actual_output = await with_timeout(receive_task, 5, "ms")

    expected_output = fir_model(input_frames)

    assert len(expected_output) == len(actual_output), (
      f"Frame count mismatch: received {len(actual_output)}, "
      f"expected {len(expected_output)}"
    )

    for index, (expected, actual) in enumerate(
        zip(expected_output, actual_output)
    ):
      actual = tuple(int(value) for value in actual)
      expected = tuple(int(value) for value in expected)

      assert expected == actual,(
        f"First mismatch at frame: {index}\n"
        f"Received: {actual}. Expected: {expected}"
    )
      
@cocotb.test()
async def multiple_frame(dut):

    await clock_start(dut, dsp_period= DSP_CLK, i2s_period = I2S_CLK)

    await reset(dut)

    input_frames = []

    for i in range (100):   

        input_frames.append((i,-i))

    receive_task = cocotb.start_soon(receive_fir_output(dut, len(input_frames)))
    send_task = cocotb.start_soon(send_frames(dut, input_frames))

    await send_task
    actual_output = await with_timeout(receive_task, 5, "ms")

    expected_output = fir_model(input_frames)

    assert len(expected_output) == len(actual_output), (
      f"Frame count mismatch: received {len(actual_output)}, "
      f"expected {len(expected_output)}"
    )

    for index, (expected, actual) in enumerate(
        zip(expected_output, actual_output)
    ):
      actual = tuple(int(value) for value in actual)
      expected = tuple(int(value) for value in expected)

      assert expected == actual,(
        f"First mismatch at frame: {index}\n"
        f"Received: {actual}. Expected: {expected}"
    )
        



