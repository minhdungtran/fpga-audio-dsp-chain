import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly

SCK_PERIOD_NS = 10
WIDTH = 24


def mask(width: int) -> int:
    return (1 << width) - 1


async def reset_dut(dut):

    dut.reset.value = 1
    dut.SD.value = 0

    for _ in range(3):
        await RisingEdge(dut.sck)

    dut.reset.value = 0
    await RisingEdge(dut.sck)

async def initialize_i2s_frame_sync(dut):

    dut.WS.value = 0
    await RisingEdge(dut.sck)

    await FallingEdge(dut.sck)
    dut.WS.value = 1
    await RisingEdge(dut.sck)

async def send_i2s_word(dut, WS_value: int, word: int, width: int = WIDTH):

    word &= mask(width)

    await FallingEdge(dut.sck)
    dut.WS.value = WS_value
    dut.SD.value = 0

    await RisingEdge(dut.sck)

    for i in range(width - 1, -1, -1):
        await FallingEdge(dut.sck)
        dut.SD.value = (word >> i) & 1
        await RisingEdge(dut.sck)


async def wait_for_done_and_check(dut, expected_left: int, expected_right: int, width: int = WIDTH):

    for _ in range(8):
        await RisingEdge(dut.sck)
        await ReadOnly()

        if int(dut.data_ready.value) == 1:
            got_left = int(dut.output_LD.value)
            got_right = int(dut.output_RD.value)

            assert got_left == (expected_left & mask(width)),(
              f"Left sample mismatch: got {hex(got_left)}, expected {hex(expected_left & mask(width))}"
            )

            assert got_right == (expected_right & mask(width)), (
              f"Right sample mismatch: got {hex(got_right)}, expected {hex(expected_right & mask(width))}"
            )
            
            await RisingEdge(dut.sck)
            await ReadOnly()

            assert int(dut.data_ready.value) == 0,(
              f"data_ready should only pulse high for 1 cycle"
            )

            assert int(dut.output_LD.value) == got_left, (
              f"output_LD changed immediately after data_ready"
            )

            assert int(dut.output_RD.value) == got_right, (
              f"output_RD changed immediately after data_ready"
            )
            return

    raise AssertionError("Timed out waiting for data_ready")


@cocotb.test()
async def basic(dut):

    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, units="ns").start())

    await reset_dut(dut)
    await initialize_i2s_frame_sync(dut)

    frames = [
    (0x000000, 0x000000),  # silence
    (0xFFFFFF, 0xFFFFFF),  # all ones
    (0xAAAAAA, 0x555555),  # alternating bits
    (0x555555, 0xAAAAAA),  # opposite alternating bits
    (0x800000, 0x7FFFFF),  # signed boundary
    (0x000001, 0x000001),  # LSB only
]
    for left, right in frames:
      await send_i2s_word(dut, 0, left)
      await send_i2s_word(dut, 1, right)

      await wait_for_done_and_check(dut, left, right)


@cocotb.test()
async def multiple(dut):

    cocotb.start_soon(Clock(dut.sck, SCK_PERIOD_NS, units="ns").start())

    await reset_dut(dut)
    await initialize_i2s_frame_sync(dut)

    random.seed(1)

    for _ in range(100):
        left = random.getrandbits(WIDTH)
        right = random.getrandbits(WIDTH)

        await send_i2s_word(dut, 0, left)
        await send_i2s_word(dut, 1, right)

        await wait_for_done_and_check(dut, left, right)
        
    
    