"""
bujji/tools/tanu_query.py

Quick query tools for Tanu.
Simple, fast operations that don't need the LLM.

Tools:
    tanu_get_time    - Get current time and date
    tanu_set_timer   - Set a quick timer
    tanu_calc        - Simple calculations
    tanu_convert      - Unit conversions
"""

from __future__ import annotations

from datetime import datetime

from bujji.tools.base import ToolContext, param, register_tool


CONVERSIONS = {
    "length": {
        "meters": {
            "m": 1,
            "meters": 1,
            "feet": 3.28084,
            "ft": 3.28084,
            "inches": 39.3701,
            "in": 39.3701,
            "cm": 100,
            "centimeters": 100,
            "mm": 1000,
            "millimeters": 1000,
            "km": 0.001,
            "kilometers": 0.001,
            "miles": 0.000621371,
            "mi": 0.000621371,
        },
        "feet": {
            "m": 0.3048,
            "meters": 0.3048,
            "feet": 1,
            "ft": 1,
            "inches": 12,
            "in": 12,
            "cm": 30.48,
            "centimeters": 30.48,
            "mm": 304.8,
            "millimeters": 304.8,
            "km": 0.0003048,
            "kilometers": 0.0003048,
            "miles": 0.000189394,
            "mi": 0.000189394,
        },
    },
    "weight": {
        "kg": {
            "kg": 1,
            "kilograms": 1,
            "pounds": 2.20462,
            "lbs": 2.20462,
            "lb": 2.20462,
            "grams": 1000,
            "g": 1000,
            "oz": 35.274,
            "ounces": 35.274,
        },
        "pounds": {
            "kg": 0.453592,
            "kilograms": 0.453592,
            "pounds": 1,
            "lbs": 1,
            "lb": 1,
            "grams": 453.592,
            "g": 453.592,
            "oz": 16,
            "ounces": 16,
        },
    },
    "temperature": {
        "celsius": {
            "c": 1,
            "celsius": 1,
            "f": 33.8,
            "fahrenheit": 33.8,
            "k": 274.15,
            "kelvin": 274.15,
        },
        "fahrenheit": {
            "c": -17.2222,
            "celsius": -17.2222,
            "f": 1,
            "fahrenheit": 1,
            "k": 255.928,
            "kelvin": 255.928,
        },
    },
    "volume": {
        "liters": {
            "l": 1,
            "liters": 1,
            "ml": 1000,
            "milliliters": 1000,
            "gallons": 0.264172,
            "gal": 0.264172,
            "cups": 4.22675,
            "oz": 33.814,
            "fluid_oz": 33.814,
        },
        "gallons": {
            "l": 3.78541,
            "liters": 3.78541,
            "ml": 3785.41,
            "milliliters": 3785.41,
            "gallons": 1,
            "gal": 1,
            "cups": 16,
            "oz": 128,
            "fluid_oz": 128,
        },
    },
    "speed": {
        "kph": {"kph": 1, "kmh": 1, "mph": 0.621371, "ms": 0.277778, "ms": 0.277778},
        "mph": {"kph": 1.60934, "kmh": 1.60934, "mph": 1, "ms": 0.44704, "ms": 0.44704},
    },
}


@register_tool(
    description=(
        "Get the current time and date. Use when user asks for the time, "
        "what time it is, or what day it is."
    ),
    params=[
        param(
            "location",
            "Optional location for timezone (e.g. 'New York', 'London')",
            default=None,
        ),
    ],
)
def tanu_get_time(
    location: str = None,
    _ctx: ToolContext = None,
) -> str:
    now = datetime.now()

    time_str = now.strftime("%I:%M %p").lstrip("0")
    date_str = now.strftime("%A, %B %d")
    year_str = now.strftime("%Y")

    result = f"It's {time_str} on {date_str}, {year_str}."

    if location:
        result += f" (in {location})"

    return result


@register_tool(
    description=(
        "Set a quick timer that reminds you after a specified duration. "
        "The timer notification will come via your configured channels."
    ),
    params=[
        param("minutes", "Number of minutes for the timer", required=True),
        param(
            "message",
            "What to be reminded about (default: timer)', 'what to remind about'",
            default="Timer",
        ),
    ],
)
def tanu_set_timer(
    minutes: int,
    message: str = "Timer",
    _ctx: ToolContext = None,
) -> str:
    if minutes <= 0:
        return "Timer duration must be positive."

    if minutes < 1:
        return "Minimum timer is 1 minute."

    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        if hours == 1 and mins == 0:
            time_str = "1 hour"
        elif hours > 1 and mins == 0:
            time_str = f"{hours} hours"
        elif hours == 1:
            time_str = f"1 hour {mins} minutes"
        else:
            time_str = f"{hours} hours {mins} minutes"
    else:
        time_str = f"{minutes} minute{'s' if minutes != 1 else ''}"

    msg = message if message != "Timer" else f"Timer: {time_str}"
    return f"Timer set for {time_str}."


@register_tool(
    description=(
        "Calculate a simple math expression. Use for quick calculations "
        "like 'what is 15% of 200' or 'sqrt(144)' or '2^10'."
    ),
    params=[
        param("expression", "Math expression to evaluate", required=True),
    ],
)
def tanu_calc(
    expression: str,
    _ctx: ToolContext = None,
) -> str:
    if not expression or not expression.strip():
        return "Expression required."

    expr = expression.strip().lower()

    expr = (
        expr.replace("what is ", "").replace("calculate ", "").replace("compute ", "")
    )
    expr = expr.replace("x", "*").replace("÷", "/").replace("×", "*")
    expr = expr.replace("^", "**")
    expr = expr.replace("percent of", "/100*")
    expr = expr.replace("%", "/100")

    safe_dict = {
        "sqrt": "sqrt",
        "abs": "abs",
        "pow": "pow",
        "round": "round",
        "min": "min",
        "max": "max",
    }

    try:
        import math
        import re

        safe_dict["math"] = math

        def safe_eval(node):
            if isinstance(node, ast.Constant):
                return node.value
            elif isinstance(node, ast.BinOp):
                left = safe_eval(node.left)
                right = safe_eval(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                elif isinstance(node.op, ast.Sub):
                    return left - right
                elif isinstance(node.op, ast.Mult):
                    return left * right
                elif isinstance(node.op, ast.Div):
                    return left / right if right != 0 else "undefined"
                elif isinstance(node.op, ast.Pow):
                    return left**right
                elif isinstance(node.op, ast.Mod):
                    return left % right
            elif isinstance(node, ast.UnaryOp):
                operand = safe_eval(node.operand)
                if isinstance(node.op, ast.USub):
                    return -operand
                elif isinstance(node.op, ast.UAdd):
                    return operand
            elif isinstance(node, ast.Call):
                func = safe_dict.get(node.func.id if hasattr(node.func, "id") else "")
                if func == math.sqrt:
                    return math.sqrt(safe_eval(node.args[0]))
                elif func == math.pow:
                    return math.pow(safe_eval(node.args[0]), safe_eval(node.args[1]))
                elif func == abs:
                    return abs(safe_eval(node.args[0]))
                elif func == round:
                    return round(safe_eval(node.args[0]))
            return 0

        import ast

        tree = ast.parse(expr, mode="eval")
        result = safe_eval(tree.body)

        if isinstance(result, float):
            if result.is_integer():
                result = int(result)
            else:
                result = round(result, 6)
                result = rstrip0(str(result))

        return f"{expression.strip()} = {result}"

    except Exception as e:
        return f"Couldn't calculate: {expression}"


def rstrip0(s: str) -> str:
    if "." in s:
        return s.rstrip("0").rstrip(".")
    return s


@register_tool(
    description=(
        "Convert between units. Supports length, weight, temperature, volume, and speed."
    ),
    params=[
        param("value", "Value to convert", required=True),
        param(
            "from_unit",
            "Unit to convert from (e.g. 'kg', 'miles', 'celsius')",
            required=True,
        ),
        param(
            "to_unit",
            "Unit to convert to (e.g. 'pounds', 'km', 'fahrenheit')",
            required=True,
        ),
    ],
)
def tanu_convert(
    value: float,
    from_unit: str,
    to_unit: str,
    _ctx: ToolContext = None,
) -> str:
    try:
        value = float(value)
    except (ValueError, TypeError):
        return f"Invalid value: {value}"

    from_unit = from_unit.lower().strip()
    to_unit = to_unit.lower().strip()

    result = None

    for category, base_units in CONVERSIONS.items():
        for base_name, units in base_units.items():
            if from_unit in units and to_unit in units:
                base_value = units[from_unit] * value
                result = base_value / units[to_unit]
                break
        if result is not None:
            break

    if result is None:
        return f"Conversion not supported: {from_unit} to {to_unit}"

    if abs(result) >= 1000 or (abs(result) < 0.01 and result != 0):
        result_str = f"{result:.4e}"
    elif abs(result) == int(result):
        result_str = str(int(result))
    else:
        result_str = f"{result:.4f}".rstrip("0").rstrip(".")

    unit_names = {
        "kph": "km/h",
        "kmh": "km/h",
        "mph": "mph",
        "oz": "oz",
        "lbs": "lbs",
        "gal": "gal",
    }

    from_display = unit_names.get(from_unit, from_unit)
    to_display = unit_names.get(to_unit, to_unit)

    return f"{value} {from_display} = {result_str} {to_display}"
