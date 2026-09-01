import random as pyrandom
import cocotb
import numpy as np
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from pathlib import Path

CLK_PERIOD_NS = 10
WIDTH = 24
COEFFICIENT_WIDTH = 16
FRAC_BITS = 15
NUM_TAPS = 63

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


async def reset(dut):
    await RisingEdge(dut.clk)
    dut.reset.value = 1

    await RisingEdge(dut.clk)

    dut.reset.value = 0
    for _ in range(65):
        await RisingEdge(dut.clk)

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

async def send_frames(dut, input_frame):
    actual_output = []
    for left, right in input_frame:
        dut.in_LD.value = int_to_two_compliment(left, WIDTH)
        dut.in_RD.value = int_to_two_compliment(right,WIDTH)
        dut.data_valid.value = 1
        await RisingEdge(dut.clk)
        dut.data_valid.value = 0

        for _ in range(140):
            await RisingEdge(dut.clk)
            if dut.data_ready.value == 1:
                actual_left = two__compliment_to_int(int(dut.out_LD.value),WIDTH)
                actual_right = two__compliment_to_int(int(dut.out_RD.value),WIDTH)

                actual_output.append((actual_left, actual_right))
        
    return actual_output
        
async def wait_for_output(dut, timeout_cycles=200):
    for cycle in range(timeout_cycles):
        await RisingEdge(dut.clk)

        if int(dut.data_ready.value) == 1:
            return cycle + 1

@cocotb.test()
async def multiple_random(dut):

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
   
    input_frame = []
    
    for _ in range(200):
        left = pyrandom.randint(MIN_24, MAX_24)
        right = pyrandom.randint(MIN_24, MAX_24)
        input_frame.append((left,right))

    await reset(dut)

    actual_outputs = await send_frames(dut, input_frame)

    expected_outputs = fir_model(input_frame)

    assert len(actual_outputs) == len(expected_outputs)

    for frame_number, (expected, actual) in enumerate(
        zip(expected_outputs, actual_outputs)
    ):
        assert actual == expected, (
            f"Frame {frame_number}: "
            f"expected={expected}, actual={actual}"
        )


@cocotb.test()
async def all_zero(dut):

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
   
    input_frame = []
    
    for _ in range(80):
        left = 0x0
        right = 0x0
        input_frame.append((left,right))

    await reset(dut)

    actual_outputs = await send_frames(dut, input_frame)

    expected_outputs = fir_model(input_frame)

    assert len(actual_outputs) == len(expected_outputs)

    for left, right in actual_outputs:
        assert left == 0, (
            "Left output should be all zero"
        )
        assert right == 0, (
            "Right output should be all zero"
        )
    
    await reset(dut)
    
    for k in range(NUM_TAPS):
      assert dut.l_cir_ram.value[k] == 0, (
          "Left output should be all zero"
      )
      assert dut.r_cir_ram.value[k] == 0, (
          "Right output should be all zero"
      )


@cocotb.test()
async def impulse_on_each_channel(dut):

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

    IMPULSE = (1 << FRAC_BITS)
   
    left_input_frame = (
        [(IMPULSE,0)] + [(0,0)]*(NUM_TAPS+5)
    )
    right_input_frame = (
        [(0, IMPULSE)] + [(0,0)]*(NUM_TAPS+5)
    )

    await reset(dut)
    
    actual_left_outputs = await send_frames(dut, left_input_frame)
    actual_right_outputs = await send_frames(dut, right_input_frame)

    assert len(left_input_frame) == len(actual_left_outputs)
    assert len(right_input_frame) == len(actual_right_outputs)
    
    for tap in range(NUM_TAPS):    
      expected_output = processing(coefficients[tap]*IMPULSE) 
      left,right = actual_left_outputs[tap]
      assert left== expected_output,(
        f"At tap {tap}\n"
        f"Got: {left}\n"
        f"Expect: {expected_output}"
    )
      assert right == 0, (
        f"At tap {tap}\n"
        f"Got: {left}\n" 
      )
      
    # The impulse response must end after 63 taps.
    for frame in range(NUM_TAPS, len(actual_left_outputs)):
        assert actual_left_outputs[frame] == (0, 0), (
            f"Unexpected output after final tap at frame {frame}: "
            f"{actual_left_outputs[frame]}"
        )

    for tap in range(NUM_TAPS):    
      expected_output = processing(coefficients[tap]*IMPULSE) 
      left,right = actual_right_outputs[tap]
      assert right== expected_output,(
        f"At tap {tap}\n"
        f"Got: {right}\n"
        f"Expect: {expected_output}"
    )
      assert left == 0, (
        f"At tap {tap}\n"
        f"Got: {left}\n" 
      )

    # The impulse response must end after 63 taps.
    for frame in range(NUM_TAPS, len(actual_right_outputs)):
        assert actual_right_outputs[frame] == (0, 0), (
            f"Unexpected output after final tap at frame {frame}: "
            f"{actual_right_outputs[frame]}"
        )


@cocotb.test()
async def timing_handshake(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

    await reset(dut)

    dut.in_LD.value = int_to_two_compliment(10, WIDTH)
    dut.in_RD.value = int_to_two_compliment(20, WIDTH)
    dut.data_valid.value = 1

    await RisingEdge(dut.clk)
    dut.data_valid.value = 0

    latency = await wait_for_output(dut, timeout_cycles=200)

    dut._log.info(
        f"data_ready received after {latency} cycles"
    )

    assert int(dut.data_ready.value) == 1

    await RisingEdge(dut.clk)

    assert int(dut.data_ready.value) == 0, (
        "data_ready must be a one-cycle pulse"
    )

   






        

        
    


            
