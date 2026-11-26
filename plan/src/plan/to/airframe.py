from dataclasses import dataclass
from typing import List, Dict


# Define the Trim class
@dataclass
class Trim:
    MinCG: float
    MaxCG: float
    MinTrim: float
    MaxTrim: float


# Define the Takeoff class
@dataclass
class Takeoff:
    RotateISA: int
    WeightReferenceISA: List[int]
    TakeoffDistanceTable: List[int]
    TakeoffDistanceTableISA: List[int]
    AltitudeAdjustment: int
    TMAXFlex: int
    TREFAICE: int
    ThrustMultiplier: int
    FlapsMultiplier: List[float]
    TakeoffRef2Alt2000: int
    TakeoffRef2Alt4000: int
    TakeoffRef2Alt6000: int
    TakeoffRef2Alt8000: int


# Define the Landing class
@dataclass
class Landing:
    WeightReferenceISA: List[int]
    DistanceReferenceISA: List[int]
    FlapsMultiplier: List[float]
    RunwayConditionMultiplier: List[float]
    AltitudeCorrectionTable: List[int]
    StopDistanceDiffs: List[int]


# Define the Airframe class
@dataclass
class Airframe:
    name: str
    engines: str
    mtow: int
    oew: int
    mlw: int
    ISAIncrease: int
    trim: Trim
    Takeoff: Takeoff
    landing: Landing
    VSpeeds: Dict[str, Dict[int, int]]  # Directly use a dictionary for VSpeeds
    # Landing VLS in kt by config ("FULL", "3") and weight in tonnes
    VLS: Dict[str, Dict[int, int]]
    # Multiplier applied to VLS, to tune the table against the aircraft
    VLSScale: float = 1.0

    def vls(self, conf: str, weight_kg: float) -> float:
        """VLS in kt, linearly interpolated by weight and clamped to the table"""
        table = self.VLS[conf]
        weights = sorted(table)
        tonnes = min(max(weight_kg / 1000, weights[0]), weights[-1])
        for low, high in zip(weights, weights[1:]):
            if tonnes <= high:
                f = (tonnes - low) / (high - low)
                speed = table[low] + f * (table[high] - table[low])
                break
        else:
            speed = table[weights[-1]]
        return speed * self.VLSScale


# Create the A20N instance
a20n = Airframe(
    name="A20N",
    engines="LEAP-1A",
    mtow=79000,
    oew=42500,
    mlw=67400,
    ISAIncrease=15,
    trim=Trim(MinCG=17, MaxCG=40, MinTrim=-2.5, MaxTrim=3.8),
    Takeoff=Takeoff(
        RotateISA=142,
        WeightReferenceISA=[50000, 75000, 85000],
        TakeoffDistanceTable=[1000, 1690, 2300],
        TakeoffDistanceTableISA=[1050, 1750, 2390],
        AltitudeAdjustment=100,
        TMAXFlex=60,
        TREFAICE=30,
        ThrustMultiplier=10031,
        FlapsMultiplier=[10, 1e-7, -5],
        TakeoffRef2Alt2000=1770,
        TakeoffRef2Alt4000=1920,
        TakeoffRef2Alt6000=2050,
        TakeoffRef2Alt8000=2330,
    ),
    landing=Landing(
        WeightReferenceISA=[50000, 60000, 70000],
        DistanceReferenceISA=[1143, 1341, 1621],
        FlapsMultiplier=[1, 1.2, 1.15, 1.1],
        RunwayConditionMultiplier=[0, 0.15],
        AltitudeCorrectionTable=[2000, 4000, 6000, 8000, 10000],
        StopDistanceDiffs=[61, 61, 91, 168, 178],
    ),
    VSpeeds={
        "1": {
            35: 126,
            40: 126,
            45: 126,
            50: 127,
            55: 127,
            60: 132,
            65: 137,
            70: 142,
            75: 147,
            80: 152,
        },
        "2": {
            35: 126,
            40: 126,
            45: 126,
            50: 126,
            55: 127,
            60: 127,
            65: 132,
            70: 137,
            75: 141,
            80: 146,
        },
        "3": {
            35: 125,
            40: 125,
            45: 125,
            50: 125,
            55: 125,
            60: 128,
            65: 129,
            70: 132,
            75: 141,
            80: 141,
        },
    },
    # Estimated: 70t figures from a forum post, scaled by sqrt(weight)
    VLS={
        "FULL": {40: 102, 45: 108, 50: 114, 55: 120, 60: 125, 65: 130, 70: 135, 75: 140, 79: 143},
        "3": {40: 110, 45: 117, 50: 123, 55: 129, 60: 135, 65: 141, 70: 146, 75: 151, 79: 155},
    },
    VLSScale=1.06,
)

# Accessing example data
# print(a20n.name)
# print(a20n.Takeoff.RotateISA)
# print(a20n.vspeeds["1"][35])
