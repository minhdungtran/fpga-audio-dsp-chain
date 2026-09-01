"""
Manual WS-driven I2S transmitter testbench.

This testbench manually controls WS transitions to verify transmitter
functionality without using a continuously generated WS clock. An initial
WS 1 -> 0 transition is applied after reset to satisfy the DUT's frame
synchronization logic. WS is then returned to the idle/right-channel state so
each test frame begins with a clean WS 1 -> 0 transition, matching the standard
I2S left-channel frame start.
"""

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge

SCK_PERIOD_NS = 10
WIDTH = 24


async def reset(dut):

    dut.reset.value = 1
    dut.input_LD.value = 0
    dut.input_RD.value = 0
    dut.WS.value = 1

    for _ in range(3):
        await FallingEdge(dut.sck)

    dut.reset.value = 0
    await FallingEdge(dut.sck)

async def initialize_i2s_frame_sync(dut):
    """
    Mimicks the frame synchronization of the transmitter
    It starts working at the first FallingEdge of WS clock
    dut.frame_synchronization.value = 1 after this
    """

    dut.WS.value = 1
    await FallingEdge(dut.sck)

    dut.WS.value = 0
    await FallingEdge(dut.sck)



async def pulse_sample_valid(dut, left, right):
    dut.input_LD.value = left
    dut.input_RD.value = right
    dut.data_valid.value = 1
    await FallingEdge(dut.sck)
    dut.data_valid.value = 0


async def receive_i2s_word(dut, WS, width =WIDTH):
    
    dut.WS.value = WS
    await FallingEdge(dut.sck) # as there is 1 cycle delay
    await FallingEdge(dut.sck) # another cycle as right now SD is assigned to = MSB

    output = 0

    for i in range(width-1,-1,-1):
        await RisingEdge(dut.sck) # as transmitter changes SD in fallingEdge, so we can sample safely on risingEdge
        bit = int(dut.SD.value)
        output = output | (bit << i)
    return output
    
async def reconstruct_i2s_word(dut, width = WIDTH):
    await FallingEdge(dut.sck) 

    output = 0

    for i in range(width-1,-1,-1):
        await RisingEdge(dut.sck) # as transmitter changes SD in fallingEdge, so we can sample safely on risingEdge
        bit = int(dut.SD.value)
        output = output | (bit << i)
    return output

@cocotb.test()
async def basic(dut):
    """
    check if the transmitter works for some special cases
    """

    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())
   
    await reset(dut)
    await initialize_i2s_frame_sync(dut)

    dut.WS.value = 1
    await FallingEdge(dut.sck)
    
    frames = [
    (0x000000, 0x000000),  # silence
    (0xFFFFFF, 0xFFFFFF),  # all ones
    (0xAAAAAA, 0x555555),  # alternating bits
    (0x555555, 0xAAAAAA),  # opposite alternating bits
    (0x800000, 0x7FFFFF),  # signed boundary
    (0x000001, 0x000001),  # LSB only
    ]

    for left, right in frames:
        await pulse_sample_valid(dut, left, right)
        
        result_L = await receive_i2s_word(dut, 0, WIDTH)
        assert left == result_L, (
        f"Left Output Mismatch."
        f"Supposed to get {hex(left)}, but got {hex(result_L)}"
        )
    
        result_R = await receive_i2s_word(dut, 1, WIDTH)
        assert right == result_R, (
        f"Right Output Mismatch."
        f"Supposed to get {hex(right)}, but got {hex(result_R)}"
        )



@cocotb.test()
async def multiple(dut):
    """
    check if the transmitter works for many random frames
    """
    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())
   
    await reset(dut)
    await initialize_i2s_frame_sync(dut)

    dut.WS.value = 1
    await FallingEdge(dut.sck)

    random.seed(1)

    for i in range(100):
        left = random.getrandbits(WIDTH)
        right = random.getrandbits(WIDTH)

        await pulse_sample_valid(dut, left, right)
        
        result_L = await receive_i2s_word(dut, 0, WIDTH)
        assert left == result_L, (
        f"Left Output Mismatch."
        f"Supposed to get {hex(left)}, but got {hex(result_L)}"
        )
    
        result_R = await receive_i2s_word(dut, 1, WIDTH)
        assert right == result_R, (
        f"Right Output Mismatch."
        f"Supposed to get {hex(right)}, but got {hex(result_R)}"
        )

@cocotb.test()
async def sample_updates_only_on_frame_boundary(dut):
    """
    Verify that a new pending sample is loaded only at the next stereo frame boundary
    (WS 1 -> 0), not during the current right-channel period.
    """
    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())

    await reset(dut)
    await initialize_i2s_frame_sync(dut)

    dut.WS.value = 1
    await FallingEdge(dut.sck)

    OLD_L = 0xFFFFFF
    OLD_R = 0x000121
    NEW_L = 0x000444
    NEW_R = 0x000234
    
    # The left side receive and output the old left sample
    await pulse_sample_valid(dut, OLD_L, OLD_R)

    await receive_i2s_word(dut, 0, WIDTH)

    # Start one cycle delay before transmitting the right channel
    dut.WS.value = 1

    await pulse_sample_valid(dut, NEW_L, NEW_R)

    # Check if old right data is properly received
    right = await reconstruct_i2s_word(dut, WIDTH)
    assert right == OLD_R, (
        f"The transmitter do not load new sample at WS = 1"
        f"Supposed to get {hex(OLD_R)}, but got {hex(right)}"
    )

    left_2 = await receive_i2s_word(dut, 0,  WIDTH)
    assert left_2 == NEW_L, (
        f"The transmitter does not load new samples as expected."
        f"Supposed to get {hex(NEW_L)}, but got {hex(left_2)}"
    )

    right_2 = await receive_i2s_word(dut, 1, WIDTH)
    assert right_2 == NEW_R, (
        f"The transmitter does not load new samples as expected."
        f"Supposed to get {hex(NEW_R)}, but got {hex(right_2)}"
    )


@cocotb.test()
async def i2s_one_clock_delay_after_ws_edge(dut):
    """
    Check if transmitter follow the 1 clock delay rule
    """

    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())

    await reset(dut)
    await initialize_i2s_frame_sync(dut)

    dut.WS.value = 1
    await FallingEdge(dut.sck)

    await pulse_sample_valid(dut, 0x800000, 0x000000)

    # Data to internal registers + 1 cycle delay
    dut.WS.value = 0 
    await FallingEdge(dut.sck)
    
    # Get MSB to SD
    await FallingEdge(dut.sck)
    await FallingEdge(dut.sck)
    
    assert dut.SD.value == 0x1,(
        f"I2S needs to have 1 clock delay after WS clock edge"
    )

@cocotb.test()
async def pending_sample_overwrite_uses_latest_sample(dut):
    """
    if two data_valid pulses happen before the next WS 1 -> 0, 
    the second sample overwrites the first.   
    """
    OLD_L = 0xFFFFFF
    OLD_R = 0x000121
    NEW_L = 0x000444
    NEW_R = 0x000234

    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())

    await reset(dut)
    await initialize_i2s_frame_sync(dut)

    dut.WS.value = 1
    await FallingEdge(dut.sck)

    await pulse_sample_valid(dut, OLD_L, OLD_R)

    for _ in range(10):
        await FallingEdge(dut.sck)

    await pulse_sample_valid(dut, NEW_L, NEW_R)

    left = await receive_i2s_word(dut, 0,  WIDTH)
    assert left == NEW_L, (
        f"The transmitter does not overwrite old samples."
        f"Supposed to get {hex(NEW_L)}, but got {hex(left)}"
    )

    right = await receive_i2s_word(dut, 1, WIDTH)
    assert right == NEW_R, (
        f"The transmitter does not overwrite old samples."
        f"Supposed to get {hex(NEW_R)}, but got {hex(right)}"
    )


@cocotb.test()
async def outputs_zero_after_reset_without_sample(dut):
    """
    After reset, with no sample loaded, SD stays zero.
    """

    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, unit="ns").start())

    await reset(dut)
    await initialize_i2s_frame_sync(dut)

    dut.WS.value = 1
    await FallingEdge(dut.sck)

    assert dut.SD.value ==0,(
        f"After reset, SD should start clean at 0"
    )
    
    dut.WS.value = 1
    dut.input_LD.value = 0xFFFFFF
    dut.input_RD.value = 0xFFFFFF
    dut.data_valid.value = 0

    for _ in range(3):
        await FallingEdge(dut.sck)
        assert int(dut.SD.value) == 0 ,(
            f"SD should stay at 0 when data_valid is low"
        )





