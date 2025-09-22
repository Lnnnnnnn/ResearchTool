from dataclasses import dataclass
from typing import Tuple, Literal
import math

Overflow = Literal["wrap", "saturate"]
Rounding = Literal["nearest", "floor", "ceil"]


@dataclass
class FixedFormat:
    """定点数格式：W 总位宽、F 小数位、signed 是否有符号（补码）"""
    W: int
    F: int
    signed: bool = True

    @property
    def scale(self) -> int:  # 2^F
        return 1 << self.F

    @property
    def modulus(self) -> int:  # 2^W
        return 1 << self.W

    @property
    def min_int(self) -> int:  # 可表示的最小整数（补码）
        return -(1 << (self.W - 1)) if self.signed else 0

    @property
    def max_int(self) -> int:  # 可表示的最大整数（补码）
        return (1 << (self.W - 1)) - 1 if self.signed else (1 << self.W) - 1

    @property
    def resolution(self) -> float:
        return 1.0 / self.scale

    @property
    def min_real(self) -> float:
        return self.min_int / self.scale

    @property
    def max_real(self) -> float:
        return self.max_int / self.scale


# ---------- 基础转换 ----------
def _round_to_int(x: float, fmt: FixedFormat, rounding: Rounding) -> int:
    """把实数乘以 2^F 后，按指定方式取整为整数"""
    y = x * fmt.scale
    if rounding == "nearest":
        return int(round(y))
    elif rounding == "floor":
        return math.floor(y)
    elif rounding == "ceil":
        return math.ceil(y)
    else:
        raise ValueError("rounding 只能是 'nearest' | 'floor' | 'ceil'")


def _apply_overflow(qi: int, fmt: FixedFormat, overflow: Overflow) -> int:
    """把整数 qi 约束到格式范围内：wrap 模 2^W；saturate 切边"""
    if overflow == "wrap":
        qi = qi % fmt.modulus
        # 回到补码有符号范围
        if fmt.signed and qi >= (1 << (fmt.W - 1)):
            qi -= fmt.modulus
        return qi
    elif overflow == "saturate":
        return max(fmt.min_int, min(fmt.max_int, qi))
    else:
        raise ValueError("overflow 只能是 'wrap' 或 'saturate'")


def int_to_real(qi: int, fmt: FixedFormat) -> float:
    """补码整数 -> 实数"""
    # 允许输入超过范围的整数，这里先折回到合法补码
    qi = qi % fmt.modulus
    if fmt.signed and qi >= (1 << (fmt.W - 1)):
        qi -= fmt.modulus
    return qi / fmt.scale


def int_to_hex(qi: int, fmt: FixedFormat) -> str:
    """以无符号视角输出 W 位宽 16 进制（便于和硬件比对）"""
    u = qi % fmt.modulus
    width_nibbles = (fmt.W + 3) // 4
    return f"0x{u:0{width_nibbles}X}"


# ---------- 对外主函数 ----------
def quantize(
        x: float, fmt: FixedFormat, *,
        overflow: Overflow = "wrap",
        rounding: Rounding = "nearest"
) -> Tuple[int, float, str]:
    """
    实数 x -> 定点：返回 (存储整数 qi, 解码实值 xr, 十六进制 hex_str)
    """
    qi = _round_to_int(x, fmt, rounding)
    qi = _apply_overflow(qi, fmt, overflow)
    xr = int_to_real(qi, fmt)
    return qi, xr, int_to_hex(qi, fmt)


def add(
        a: float, b: float, fmt: FixedFormat, *,
        overflow: Overflow = "wrap",
        rounding: Rounding = "nearest"
) -> Tuple[int, float, str]:
    """
    加法（先各自量化，再相加，再按 overflow 处理），返回 (qi, xr, hex)
    """
    ai = _apply_overflow(_round_to_int(a, fmt, rounding), fmt, overflow)
    bi = _apply_overflow(_round_to_int(b, fmt, rounding), fmt, overflow)
    si = ai + bi
    si = _apply_overflow(si, fmt, overflow)
    return si, int_to_real(si, fmt), int_to_hex(si, fmt)


def mul(
        a: float, b: float, fmt: FixedFormat, *,
        overflow: Overflow = "wrap",
        rounding: Rounding = "nearest"
) -> Tuple[int, float, str]:
    """
    乘法（定点约定：先量化 ai, bi；整数乘积后右移 F 位并四舍五入；再 overflow）
    """
    ai = _apply_overflow(_round_to_int(a, fmt, rounding), fmt, overflow)
    bi = _apply_overflow(_round_to_int(b, fmt, rounding), fmt, overflow)

    prod = ai * bi  # 乘完是 Q(2F)
    # 就地进行“最近”舍入：在右移前添加 2^(F-1) 的偏置（对负数也用对称偏置）
    bias = 1 << (fmt.F - 1)
    prod = prod + bias if prod >= 0 else prod - bias
    qi = prod >> fmt.F
    qi = _apply_overflow(qi, fmt, overflow)

    return qi, int_to_real(qi, fmt), int_to_hex(qi, fmt)


# ---------- 使用样例 ----------
if __name__ == "__main__":
    # 定义格式：Fix16_11（常见于 HIL/FPGA I/O）
    fmt = FixedFormat(W=16, F=11, signed=True)
    fmt32_11 = FixedFormat(W=32, F=11, signed=True)
    fmt32_17 = FixedFormat(W=32, F=17, signed=True)
    fmt16_11 = FixedFormat(W=16, F=11, signed=True)

    qi, xr, hx = quantize(762296, fmt32_11, overflow="wrap")
    print(f"[wrap] quantize(16.25) -> qi={qi}, real={xr:.6f}, hex={hx}")

    qi, xr1, hx = quantize(xr*0.016, fmt32_17, overflow="wrap")
    print(f"[wrap] quantize(16.25) -> qi={qi}, real={xr1:.6f}, hex={hx}")

    qi, xr2, hx = quantize(xr1, fmt16_11, overflow="wrap")
    print(f"[wrap] quantize(16.25) -> qi={qi}, real={xr2:.6f}, hex={hx}")

    # print("格式: Fix{}_{}  分辨率={:.6f}, 范围=[{:.6f}, {:.6f}]".format(
    #     fmt.W, fmt.F, fmt.resolution, fmt.min_real, fmt.max_real))
    #
    # # 1) 量化：回环 vs 饱和
    # for mode in ("wrap", "saturate"):
    #     qi, xr, hx = quantize(16.25, fmt, overflow=mode)  # 超过上限
    #     print(f"[{mode}] quantize(16.25) -> qi={qi}, real={xr:.6f}, hex={hx}")
    #
    # # 2) 加法示例
    # qi, xr, hx = add(10.0, 10.5, fmt, overflow="wrap")
    # print(f"[wrap] add(10.0, 10.5) -> qi={qi}, real={xr:.6f}, hex={hx}")
    #
    # qi, xr, hx = add(10.0, 10.5, fmt, overflow="saturate")
    # print(f"[saturate] add(10.0, 10.5) -> qi={qi}, real={xr:.6f}, hex={hx}")
    #
    # # 3) 乘法示例
    # qi, xr, hx = mul(5.5, 4.0, fmt, overflow="wrap")
    # print(f"[wrap] mul(5.5, 4.0) -> qi={qi}, real={xr:.6f}, hex={hx}")
    #
    # qi, xr, hx = mul(5.5, 4.0, fmt, overflow="saturate")
    # print(f"[saturate] mul(5.5, 4.0) -> qi={qi}, real={xr:.6f}, hex={hx}")
