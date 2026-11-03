from decimal import Decimal


def format_nepali(val, decimals=None):
    """
    Format a number in South Asian / Nepali numbering system:
    e.g. 6000 -> '6,000', 600000 -> '6,00,000', 2960.00 -> '2,960.00'.

    Args:
        val: int, float, Decimal, or numeric str.
        decimals:
            - None: preserve existing decimal part.
            - '-2': mimic Django floatformat:'-2' (drop .00, keep 2 decimal places if non-zero).
            - integer: exact number of decimal places (e.g. 2 -> '2,960.00').
    """
    if val is None or val == "":
        return ""

    try:
        if isinstance(val, (int, float, Decimal)):
            if decimals == "-2":
                d_val = Decimal(str(val))
                if d_val == d_val.to_integral():
                    val_str = str(int(d_val))
                else:
                    val_str = f"{d_val:.2f}"
            elif isinstance(decimals, int):
                val_str = f"{float(val):.{decimals}f}"
            else:
                if isinstance(val, Decimal):
                    val_str = f"{val:f}"
                else:
                    val_str = str(val)
        else:
            val_str = str(val).strip()
            if decimals == "-2" and "." in val_str:
                d_val = Decimal(val_str)
                if d_val == d_val.to_integral():
                    val_str = str(int(d_val))
                else:
                    val_str = f"{d_val:.2f}"
            elif isinstance(decimals, int):
                val_str = f"{float(val_str):.{decimals}f}"
    except Exception:
        val_str = str(val).strip()

    sign = ""
    if val_str.startswith("-"):
        sign = "-"
        val_str = val_str[1:]
    elif val_str.startswith("+"):
        val_str = val_str[1:]

    if "." in val_str:
        int_part, dec_part = val_str.split(".", 1)
        dec_str = "." + dec_part
    else:
        int_part = val_str
        dec_str = ""

    if not int_part.isdigit():
        return str(val)

    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last3 = int_part[-3:]
        rem = int_part[:-3]
        groups = []
        while rem:
            groups.append(rem[-2:])
            rem = rem[:-2]
        formatted_int = ",".join(reversed(groups)) + "," + last3

    return sign + formatted_int + dec_str
