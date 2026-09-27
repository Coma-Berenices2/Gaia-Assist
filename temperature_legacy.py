"""Explorer compatibility estimate, explicitly unvalidated for scientific use.

These are the existing Main.py formulas, not extensions of Casagrande's domain.
Keep separate so an emergency colour estimate never masquerades as a calibrated
temperature or a Gaia measurement.
"""
from temperature_model import number


def explorer_temperature_fallback(colour, mv=None, metallicity=None):
    x, mv, z = map(number, (colour, mv, metallicity))
    if x is None:
        return None, "Explorer fallback: BP-RP missing"
    dwarf = x > 1.8 and mv is not None and mv > 8.69
    try:
        if x < 0:
            value = 10 ** (3.978 - 1.258*x + .812*x**2 - .505*x**3)
            branch = "blue-colour relation"
        elif dwarf and z is None:
            value = 4370 - 715*x + 107*x**2 - 7.5*x**3
            branch = "red-dwarf colour relation"
        elif dwarf:
            value = 4430 - 740*x + 112*x**2 - 8*x**3 + 115*z - 25*z*x
            branch = "red-dwarf colour/metallicity relation"
        elif z is None:
            value = 9345 - 6125*x + 3381*x**2 - 1282*x**3 + 276*x**4 - 24.3*x**5
            branch = "colour-only polynomial"
        else:
            theta = .4929 + .5092*x - .0353*x**2 + .0192*z - .0020*z**2 - .0395*z*x
            value = 5040/theta
            branch = "colour/metallicity relation"
    except (OverflowError, ZeroDivisionError):
        return None, "Explorer fallback: numerical result invalid"
    value = number(value)
    if value is None or value <= 0:
        return None, "Explorer fallback: numerical result invalid"
    return value, "Explorer legacy " + branch + " (unvalidated)"
