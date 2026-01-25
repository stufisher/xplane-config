from dataclasses import dataclass
import math

from .airframe import a20n, Airframe

BARO_SEA = 1013


@dataclass
class TakeoffInstance:
    availRunway: int
    windHeading: float
    windKts: float
    tow: float
    baro: float
    oat: float
    flaps: int
    runwayHeading: float
    runwayAltitude: float
    antiIce: bool
    packs: bool
    toga: bool
    runwayCondition: float
    isKG: bool = True
    isHP: bool = True
    isMeters: bool = False
    flex: int = 0
    requiredRunway: int = 0
    togaRequiredRunway: int = 0


@dataclass
class FlexResults:
    flex: int
    requiredRunway: int
    minFlex: int
    togaRequiredRunway: int


@dataclass
class VSpeeds:
    v1: int
    vr: int
    v2: int


class FlexMath:
    @staticmethod
    def parseQNH(qnh: int, ishpa=True):
        # workaround to allow decimal or not,
        # valid imputs become 29.92 or 2992 (inHg) or 1013 (hPa)
        if qnh - math.floor(qnh) != 0:
            qnh *= 100

        if not ishpa:
            qnh /= 2.95360316
            # convert inHg to hectopascels

        return qnh

    @staticmethod
    def parseWeight(w: int, iskg=True):
        r = w
        if not iskg:
            r = w / 2.20462262
            # convert lbs to kg

        return r

    @staticmethod
    def parseDist(d: float, ism=True):
        r = d
        if not ism:
            r = d / 3.2808399
            # convert ft to m

        return r

    @staticmethod
    def calculateDensityCorrection(
        density: float, AltCorrectionsTable: list[int], perfDistDiffTable: list[int]
    ):
        densityCorrection = 0

        for i in range(len(AltCorrectionsTable)):
            densityCorrection += (
                perfDistDiffTable[i]
                if density > AltCorrectionsTable[i]
                else ((density - AltCorrectionsTable[i - 1]) / 200)
                * (perfDistDiffTable[i] / 100)
            )

        densityCorrection += (
            0
            if density < AltCorrectionsTable[3]
            else ((density - AltCorrectionsTable[3]) / 200)
            * (perfDistDiffTable[4] / 100)
        )
        return densityCorrection if densityCorrection >= 0 else 0

    @staticmethod
    def plantSeeds(perfWeight: float, a: Airframe):
        seedModifierstd = 0
        seedModifierisa = 0

        stdSeedTable = [
            (
                (
                    (
                        a.Takeoff.TakeoffDistanceTable[1]
                        - a.Takeoff.TakeoffDistanceTable[0]
                    )
                    / (
                        a.Takeoff.WeightReferenceISA[1]
                        - a.Takeoff.WeightReferenceISA[0]
                    )
                )
                * (perfWeight - a.Takeoff.WeightReferenceISA[0])
                if perfWeight < a.Takeoff.WeightReferenceISA[1]
                else (
                    (
                        a.Takeoff.TakeoffDistanceTable[1]
                        - a.Takeoff.TakeoffDistanceTable[0]
                    )
                    / (
                        a.Takeoff.WeightReferenceISA[1]
                        - a.Takeoff.WeightReferenceISA[0]
                    )
                )
                * (a.Takeoff.WeightReferenceISA[1] - a.Takeoff.WeightReferenceISA[0])
            ),
            (
                0
                if perfWeight < a.Takeoff.WeightReferenceISA[1]
                else (
                    (
                        (
                            a.Takeoff.TakeoffDistanceTable[2]
                            - a.Takeoff.TakeoffDistanceTable[1]
                        )
                        / (
                            a.Takeoff.WeightReferenceISA[2]
                            - a.Takeoff.WeightReferenceISA[1]
                        )
                    )
                    * (perfWeight - a.Takeoff.WeightReferenceISA[1])
                    if perfWeight < a.Takeoff.WeightReferenceISA[2]
                    else (
                        (
                            a.Takeoff.TakeoffDistanceTable[2]
                            - a.Takeoff.TakeoffDistanceTable[1]
                        )
                        / (
                            a.Takeoff.WeightReferenceISA[2]
                            - a.Takeoff.WeightReferenceISA[1]
                        )
                    )
                    * (
                        a.Takeoff.WeightReferenceISA[2]
                        - a.Takeoff.WeightReferenceISA[1]
                    )
                )
            ),
            (
                0
                if perfWeight < a.Takeoff.WeightReferenceISA[2]
                else (
                    (
                        a.Takeoff.TakeoffDistanceTable[2]
                        - a.Takeoff.TakeoffDistanceTable[1]
                    )
                    / (
                        a.Takeoff.WeightReferenceISA[2]
                        - a.Takeoff.WeightReferenceISA[1]
                    )
                )
                * 1.5
                * (perfWeight - a.Takeoff.WeightReferenceISA[2])
            ),
            a.Takeoff.TakeoffDistanceTable[0],
        ]

        isaSeedTable = [
            (
                (
                    (
                        a.Takeoff.TakeoffDistanceTableISA[1]
                        - a.Takeoff.TakeoffDistanceTableISA[0]
                    )
                    / (
                        a.Takeoff.WeightReferenceISA[1]
                        - a.Takeoff.WeightReferenceISA[0]
                    )
                )
                * (perfWeight - a.Takeoff.WeightReferenceISA[0])
                if perfWeight < a.Takeoff.WeightReferenceISA[1]
                else (
                    (
                        a.Takeoff.TakeoffDistanceTableISA[1]
                        - a.Takeoff.TakeoffDistanceTableISA[0]
                    )
                    / (
                        a.Takeoff.WeightReferenceISA[1]
                        - a.Takeoff.WeightReferenceISA[0]
                    )
                )
                * (a.Takeoff.WeightReferenceISA[1] - a.Takeoff.WeightReferenceISA[0])
            ),
            (
                0
                if perfWeight < a.Takeoff.WeightReferenceISA[1]
                else (
                    (
                        (
                            a.Takeoff.TakeoffDistanceTableISA[2]
                            - a.Takeoff.TakeoffDistanceTableISA[1]
                        )
                        / (
                            a.Takeoff.WeightReferenceISA[2]
                            - a.Takeoff.WeightReferenceISA[1]
                        )
                    )
                    * (perfWeight - a.Takeoff.WeightReferenceISA[1])
                    if perfWeight < a.Takeoff.WeightReferenceISA[2]
                    else (
                        (
                            a.Takeoff.TakeoffDistanceTableISA[2]
                            - a.Takeoff.TakeoffDistanceTableISA[1]
                        )
                        / (
                            a.Takeoff.WeightReferenceISA[2]
                            - a.Takeoff.WeightReferenceISA[1]
                        )
                    )
                    * (
                        a.Takeoff.WeightReferenceISA[2]
                        - a.Takeoff.WeightReferenceISA[1]
                    )
                )
            ),
            (
                0
                if perfWeight < a.Takeoff.WeightReferenceISA[2]
                else (
                    (
                        a.Takeoff.TakeoffDistanceTableISA[2]
                        - a.Takeoff.TakeoffDistanceTableISA[1]
                    )
                    / (
                        a.Takeoff.WeightReferenceISA[2]
                        - a.Takeoff.WeightReferenceISA[1]
                    )
                )
                * 1.5
                * (perfWeight - a.Takeoff.WeightReferenceISA[2])
            ),
            a.Takeoff.TakeoffDistanceTableISA[0],
        ]

        for i in range(len(stdSeedTable)):
            seedModifierstd += stdSeedTable[i]

        for i in range(len(isaSeedTable)):
            seedModifierisa += isaSeedTable[i]

        return [seedModifierstd, seedModifierisa]

    @staticmethod
    def calculateFlapEffect(flaps: str | int, a: Airframe):
        return a.Takeoff.FlapsMultiplier[flaps - 1]

    # ported to js from https://stackoverflow.com/questions/7437660/
    @staticmethod
    def lsft(known_y: list[int], known_x: list[int], offset_x=0):
        if len(known_y) != len(known_x):
            return [0, 0]

        numPoints = len(known_y)
        x1 = 0
        y1 = 0
        xy = 0
        x2 = 0
        J = None
        M = None
        B = None

        for i in range(numPoints):
            known_x[i] -= offset_x
            x1 += known_x[i]
            y1 += known_y[i]
            xy += known_x[i] * known_y[i]
            x2 += known_x[i] * known_x[i]

        J = numPoints * x2 - x1 * x1

        if J == 0:
            return [0, 0]

        M = (numPoints * xy - x1 * y1) / J
        B = (y1 * x2 - x1 * xy) / J

        return [M, B]

    # ported to js from https://stackoverflow.com/questions/7437660/
    @staticmethod
    def trend(known_y: list[int], known_x: list[int], new_x: list[int]):
        [m, b] = FlexMath.lsft(known_y, known_x)

        new_y = []
        for j in range(len(new_x)):
            y = m * new_x[j] + b
            new_y.append(y)

        return new_y

    # https://stackoverflow.com/a/14163874
    @staticmethod
    def growth(
        known_y: list[int], known_x: list[int], new_x: list[int], use_const=True
    ):
        tbeta: float
        talpha: float

        # calculate sums over the data:
        n = len(known_y)
        avg_x = 0
        avg_y = 0
        avg_xy = 0
        avg_xx = 0
        for i in range(n):
            x = known_x[i]
            y = math.log(known_y[i])
            avg_x += x
            avg_y += y
            avg_xy += x * y
            avg_xx += x * x

        avg_x /= n
        avg_y /= n
        avg_xy /= n
        avg_xx /= n

        # compute linear regression coefficients:
        if use_const:
            tbeta = (avg_xy - avg_x * avg_y) / (avg_xx - avg_x * avg_x)
            talpha = avg_y - tbeta * avg_x
        else:
            tbeta = avg_xy / avg_xx
            talpha = 0

        # compute and return result array:
        new_y = []
        for i in range(len(new_x)):
            new_y.append(math.exp(talpha + tbeta * new_x[i]))

        return new_y

    @staticmethod
    def knotsToMetersPerSecond(knots: float):
        return knots * 0.514444444

    @staticmethod
    def metersPerSecondToKnots(mps: float):
        return mps * 1.943844492

    @staticmethod
    def timeFromAccelerationAndDistance(metersPerSecond: float, metersTraveled: float):
        return math.sqrt(metersTraveled / metersPerSecond)

    @staticmethod
    def avergageAcceleration(metersPerSecond: float, time: float):
        return metersPerSecond / time

    @staticmethod
    def timeFromDistanceAndSpeed(metersTraveled: float, speed: float):
        return metersTraveled / speed

    @staticmethod
    def speedAtDistance(metersPerSecond: float, metersTraveled: float):
        return (
            FlexMath.timeFromAccelerationAndDistance(metersPerSecond, metersTraveled)
            * metersPerSecond
        )

    @staticmethod
    def distanceFromAccelerationAndSpeed(metersPerSecond: float, speed: float):
        return speed**2 / metersPerSecond

    @staticmethod
    def distanceFromAccelerationAndTime(metersPerSecond: float, time: float):
        return metersPerSecond * time**2

    # def sumof(array: number[]) {
    #     return array.reduce((a, b) => a + b, 0);
    # }

    @staticmethod
    def AltitudeCorrection(params: any, densityAltitude: float):
        MLAND = params.airframe.MLW
        WeightReferenceISA2 = params.airframe.Landing.WeightReferenceISA[1]
        AltitudeCorrectionTable = params.airframe.Landing.AltitudeCorrectionTable
        StopDistanceDiffs = params.airframe.Landing.StopDistanceDiffs

        def DAADJ(DA: float, BP: float):
            (DA / 2000 / 100) * (BP / 100)

        densityCorrectionsTable = [
            (
                StopDistanceDiffs[0]
                if densityAltitude > AltitudeCorrectionTable[0]
                else DAADJ(densityAltitude, StopDistanceDiffs[0])
            ),
            (
                StopDistanceDiffs[1]
                if densityAltitude > AltitudeCorrectionTable[1]
                else DAADJ(
                    densityAltitude - AltitudeCorrectionTable[1], StopDistanceDiffs[1]
                )
            ),
            (
                StopDistanceDiffs[2]
                if densityAltitude > AltitudeCorrectionTable[2]
                else DAADJ(
                    densityAltitude - AltitudeCorrectionTable[2], StopDistanceDiffs[2]
                )
            ),
            (
                StopDistanceDiffs[3]
                if densityAltitude > AltitudeCorrectionTable[3]
                else DAADJ(
                    densityAltitude - AltitudeCorrectionTable[3], StopDistanceDiffs[3]
                )
            ),
            (
                0
                if densityAltitude < AltitudeCorrectionTable[4]
                else DAADJ(
                    densityAltitude - AltitudeCorrectionTable[4], StopDistanceDiffs[4]
                )
            ),
        ]

        densityCorrectionMultiplier = (
            sum(densityCorrectionsTable) if sum(densityCorrectionsTable) > 0 else 0
        )
        AltitudeCorrectionStage1 = (densityCorrectionMultiplier / 100) * (
            params.tow / WeightReferenceISA2 / 100
        )
        return (
            AltitudeCorrectionStage1
            - (
                (
                    AltitudeCorrectionStage1
                    - (AltitudeCorrectionStage1 / 100) * (params.tow / MLAND / 100)
                )
                / 100
            )
            * 1
        )

    @staticmethod
    def calibratedDistance(params: any, densityAltitude: float):
        DistanceRequiredISATable = params.airframe.Landing.DistanceReferenceISA
        WeightReferenceISATable = params.airframe.Landing.WeightReferenceISA
        diffsTable = [
            (DistanceRequiredISATable[1] - DistanceRequiredISATable[0])
            / (WeightReferenceISATable[1] - WeightReferenceISATable[0]),
            (DistanceRequiredISATable[2] - DistanceRequiredISATable[1])
            / (WeightReferenceISATable[2] - WeightReferenceISATable[1]),
        ]
        diffsTable[2] = diffsTable[1] * 1.5

        StopDistanceRef1 = (
            diffsTable[0] * (params.tow - WeightReferenceISATable[0])
            if params.tow < WeightReferenceISATable[1]
            else diffsTable[0]
            * (WeightReferenceISATable[1] - WeightReferenceISATable[0])
        )
        StopDistanceRef2 = (
            0
            if params.tow < WeightReferenceISATable[1]
            else (
                diffsTable[1] * (params.tow - WeightReferenceISATable[1])
                if params.tow < WeightReferenceISATable[2]
                else diffsTable[1]
                * (WeightReferenceISATable[2] - WeightReferenceISATable[1])
            )
        )
        StopDistanceRef3 = (
            0
            if params.tow < WeightReferenceISATable[2]
            else diffsTable[2] * (params.tow - WeightReferenceISATable[2])
        )

        SumOfSDRefs = sum(
            [
                StopDistanceRef1,
                StopDistanceRef2,
                StopDistanceRef3,
            ]
        )
        SDRef = (
            SumOfSDRefs + DistanceRequiredISATable[0]
            if SumOfSDRefs >= 0
            else DistanceRequiredISATable[0]
        )
        return FlexMath.AltitudeCorrection(params, densityAltitude) + SDRef

    @staticmethod
    def V1SpeedVer2(
        runwayAltitude: float,
        runwayLength: float,
        runwayRequired: float,
        oat: float,
        baro: float,
        runwayCondition: float,
        windHeading: float,
        windKts: float,
        runwayHeading: float,
        flaps: float,
        tow: float,
        VR: float,
        airframe: Airframe,
    ):
        headwind = (
            math.cos((windHeading - runwayHeading * 10) * (math.pi / 180)) * windKts
        )

        params = {
            "altitude": runwayAltitude,
            "oat": oat,
            "baro": FlexMath.parseQNH(baro, False),
            "runwayCondition": runwayCondition,
            "headwind": headwind,
            "flaps": flaps,
            "tow": tow,
            "speed": 0,
            "airframe": airframe,
        }
        V1Candidate = -1
        for i in range(VR, 100, -1):
            # for (let i = VR; i >= 100; i--) {
            params.speed = i
            distance = FlexMath.calculateStopDistanceReq(params)
            distance /= 3
            # Max Manual Braking.
            time = FlexMath.timeFromDistanceAndSpeed(
                runwayRequired, FlexMath.knotsToMetersPerSecond(VR)
            )
            acc = FlexMath.avergageAcceleration(
                FlexMath.knotsToMetersPerSecond(VR), time
            )

            currDistance = FlexMath.distanceFromAccelerationAndSpeed(
                acc, FlexMath.knotsToMetersPerSecond(i)
            )
            RemainingRunway = FlexMath.parseDist(runwayLength, False) - (
                currDistance + distance
            )
            if RemainingRunway >= 0 and i > V1Candidate:
                V1Candidate = i

        return V1Candidate

    @staticmethod
    def calculateStopDistanceReq(params: any):
        flapMultiplier = params.airframe.Landing.FlapsMultiplier
        ISAIncrease = params.airframe.ISAIncrease
        altitude = params.altitude
        oat = params.oat
        baro = params.baro
        runwayCondition = params.runwayCondition
        headwind = params.headwind
        flaps: int = int(params.flaps)
        speed = params.speed

        densityAltitude = (
            altitude
            + (BARO_SEA - baro) * 27
            + (oat - (ISAIncrease - (altitude / 1000) * 2)) * 120
        )
        densityAltitude = (
            densityAltitude / 2 if densityAltitude < 0 else densityAltitude
        )

        calibratedDistance = FlexMath.calibratedDistance(params, densityAltitude)

        FlapAdjusted = calibratedDistance * flapMultiplier[flaps]
        windAdjusted: int = 0

        if headwind > 0:
            windAdjusted = (
                FlapAdjusted - ((FlapAdjusted / 100) * (headwind / (speed / 100))) / 2
            )
        else:
            windAdjusted = FlapAdjusted - (FlapAdjusted / 100) * (
                headwind / (speed / 100)
            )

        return (
            windAdjusted
            + FlexMath.calculateRCAM(windAdjusted, runwayCondition, params)
            + FlexMath.knotsToMetersPerSecond(speed) * 3  # 3 second buffer.
        )

    @staticmethod
    def calculateRCAM(distance: float, runwayCondition: float, params: any):
        runwayConditions = params.airframe.Landing.RunwayConditionMultiplier
        # dry/wet
        return distance * runwayConditions[runwayCondition]

    @staticmethod
    def round5up(x: float):
        return math.ceil(x / 5) * 5

    @staticmethod
    def round5down(x: float):
        return math.floor(x / 5) * 5

    def round10down(x: float):
        return math.floor(x / 10) * 10

    @staticmethod
    def distfrom5(x: float):
        return x - FlexMath.round5down(x)

    @staticmethod
    def altcorr(a: float):
        return math.abs(a * 2e-4)

    @staticmethod
    def f2corr(f: float, a: float):
        return abs(a * 2e-4) if f == 2 else 0

    @staticmethod
    def v2Speed(w: float, f: float, a: any, airframe: Airframe):
        v2 = airframe.VSpeeds[str(f)][FlexMath.round5down(w)]
        if v2 is None:
            v2 = airframe.VSpeeds[str(f)][FlexMath.round10down(w)]

        v2 += FlexMath.f2corr(f, a)

        V2Speed = math.ceil(v2 + FlexMath.distfrom5(w))
        return math.ceil(V2Speed)

    @staticmethod
    def vRSpeed(v2: float):
        return v2 - 4

    @staticmethod
    def v1Speed(a: float, r: float, vR: float, asd=1621):
        v1 = (asd / 2 - (a - r)) / 50
        print("v1", v1, "vr", vR)
        return vR - math.ceil(v1) if v1 > 0 else vR

    @staticmethod
    def CalculateVSpeeds(
        availRunway: float,
        requiredRunway: float,
        Weight: float,
        Flaps: float,
        RunwayAlt: float,
        isMeters: bool,
        isKG: bool,
        airframe: Airframe,
        ASD=1621,
    ):
        w = FlexMath.parseWeight(Weight, isKG) / 1000
        v2 = FlexMath.v2Speed(w, Flaps, RunwayAlt, airframe)
        vR = FlexMath.vRSpeed(v2)
        print("V1 CALC", FlexMath.parseDist(availRunway, isMeters), requiredRunway, vR, ASD)
        v1 = FlexMath.v1Speed(
            FlexMath.parseDist(availRunway, isMeters), requiredRunway, vR, ASD
        )
        return VSpeeds(
            **{
                "v1": v1,
                "vr": vR,
                "v2": v2,
            }
        )

    @staticmethod
    def calculateFlexDist(settings: TakeoffInstance, airframe: Airframe):
        density = (
            settings.runwayAltitude
            + (BARO_SEA - FlexMath.parseQNH(settings.baro, settings.isHP)) * 27
            + (settings.oat - (15 - (settings.runwayAltitude / 1000) * 2)) * 120
        )

        TREF = airframe.Takeoff.TREFAICE + (settings.runwayAltitude / 1000) * 2
        ISA = settings.oat - 15 + (settings.runwayAltitude / 1000) * 1.98

        flexTrendModifierTable = [
            settings.oat,
            0 + settings.oat - ISA,
            airframe.ISAIncrease + settings.oat - ISA,
            1 + airframe.ISAIncrease + settings.oat - ISA,
            math.floor(TREF) if TREF > settings.oat else settings.oat + 1,
            33,
            airframe.Takeoff.TMAXFlex + settings.oat - ISA,
            settings.oat,
        ]
        minFlex = flexTrendModifierTable[4]
        AltCorrectionsTable = [2000, 4000, 6000, 8000, 10000]

        perfDistDiffTable = [
            airframe.Takeoff.TakeoffRef2Alt2000
            - airframe.Takeoff.TakeoffDistanceTable[1],
            airframe.Takeoff.TakeoffRef2Alt4000 - airframe.Takeoff.TakeoffRef2Alt2000,
            airframe.Takeoff.TakeoffRef2Alt6000 - airframe.Takeoff.TakeoffRef2Alt4000,
            airframe.Takeoff.TakeoffRef2Alt8000 - airframe.Takeoff.TakeoffRef2Alt6000,
            (airframe.Takeoff.TakeoffRef2Alt8000 - airframe.Takeoff.TakeoffRef2Alt6000)
            * 1.53,
        ]

        densityCorrection = FlexMath.calculateDensityCorrection(
            density, AltCorrectionsTable, perfDistDiffTable
        )

        perfWeight = FlexMath.parseWeight(settings.tow, settings.isKG)

        altBelowToWt2ISA = (
            densityCorrection
            - (
                (
                    densityCorrection
                    - (densityCorrection / 100)
                    * (perfWeight / (airframe.Takeoff.WeightReferenceISA[1] / 100))
                )
                / 100
            )
            * airframe.Takeoff.AltitudeAdjustment
        )
        altAboveToWt2ISA = altBelowToWt2ISA
        # the correction is the same above or below for the currently implemented airframes

        distanceByDensity = (
            altBelowToWt2ISA
            if perfWeight < airframe.Takeoff.TakeoffDistanceTable[1]
            else altAboveToWt2ISA
        )

        seedModifiers = FlexMath.plantSeeds(perfWeight, airframe)

        seedModStd = seedModifiers[0]
        seedModIsa = seedModifiers[1]

        growthSeed = [
            seedModStd + distanceByDensity,
            seedModIsa + distanceByDensity,
        ]

        growthTrend = FlexMath.growth(
            growthSeed,
            [flexTrendModifierTable[1], flexTrendModifierTable[2]],
            flexTrendModifierTable,
        )

        trendBase = [
            growthTrend[0],
            growthTrend[1],
            growthTrend[2],
            math.pow(growthTrend[3], airframe.Takeoff.ThrustMultiplier / 10000),
        ]

        trendWithModifiers = FlexMath.trend(
            [trendBase[2], trendBase[3]],
            [flexTrendModifierTable[2], flexTrendModifierTable[3]],
            [
                flexTrendModifierTable[2],
                flexTrendModifierTable[3],
                flexTrendModifierTable[4],
                flexTrendModifierTable[5],
                flexTrendModifierTable[6],
                flexTrendModifierTable[7],
            ],
        )

        isaCorrection = (
            trendWithModifiers[5] if ISA > airframe.ISAIncrease else growthTrend[0]
        )

        flapCorr = isaCorrection + (isaCorrection / 100) * FlexMath.calculateFlapEffect(
            settings.flaps, airframe
        )

        headwind = (
            math.cos(
                (settings.windHeading - settings.runwayHeading * 10) * (math.pi / 180)
            )
            * settings.windKts
        )

        windLen = (
            flapCorr
            - ((flapCorr / 100) * (headwind / (airframe.Takeoff.RotateISA / 100))) / 2
            if headwind > 0
            else flapCorr
            - (flapCorr / 100) * (headwind / (airframe.Takeoff.RotateISA / 150))
        )

        totDist = windLen
        totDist += (windLen / 100) * 3 if settings.antiIce else 0
        totDist += (windLen / 100) * 4 if settings.packs else 0
        settings.togaRequiredRunway = totDist
        flapWindAIPackCorrection = totDist / (isaCorrection / 100)

        # do i need this?
        trendBase.append((growthTrend[4] / 100) * flapWindAIPackCorrection)

        distanceTrendTablePreFlex = [
            (trendWithModifiers[0] / 100) * flapWindAIPackCorrection,
            (trendWithModifiers[1] / 100) * flapWindAIPackCorrection,
            (trendWithModifiers[2] / 100) * flapWindAIPackCorrection,
            (trendWithModifiers[3] / 100) * flapWindAIPackCorrection,
            (trendWithModifiers[4] / 100) * flapWindAIPackCorrection,
            FlexMath.parseDist(settings.availRunway, settings.isMeters),
        ]

        flexTrendTable = FlexMath.trend(
            [
                flexTrendModifierTable[2],
                flexTrendModifierTable[3],
                flexTrendModifierTable[4],
                flexTrendModifierTable[5],
                flexTrendModifierTable[6],
            ],
            [
                distanceTrendTablePreFlex[0],
                distanceTrendTablePreFlex[1],
                distanceTrendTablePreFlex[2],
                distanceTrendTablePreFlex[3],
                distanceTrendTablePreFlex[4],
            ],
            distanceTrendTablePreFlex,
        )

        # this will be our final flex number.
        flexTrendTable.append(
            (
                math.floor(flexTrendTable[5])
                if flexTrendTable[5] < flexTrendTable[4]
                else math.floor(flexTrendTable[4])
            )
        )

        TakeoffDistanceTrendTable = FlexMath.trend(
            [
                distanceTrendTablePreFlex[2],
                distanceTrendTablePreFlex[3],
                distanceTrendTablePreFlex[4],
            ],
            [flexTrendTable[2], flexTrendTable[3], flexTrendTable[4]],
            [
                flexTrendTable[2],
                flexTrendTable[3],
                flexTrendTable[4],
                flexTrendTable[5],
                flexTrendTable[6],
            ],
        )

        settings.flex = -1 if settings.toga else flexTrendTable[6]
        settings.requiredRunway = (
            settings.togaRequiredRunway
            if settings.toga
            else TakeoffDistanceTrendTable[4]
        )
        return FlexResults(
            **{
                "flex": settings.flex,
                "requiredRunway": settings.requiredRunway,
                "minFlex": minFlex,
                "togaRequiredRunway": settings.togaRequiredRunway,
            }
        )


def calculate_trim(cg: float):
    error = cg < a20n.trim.MinCG or cg > a20n.trim.MaxCG
    magic1 = (a20n.trim.MinTrim - a20n.trim.MaxTrim) / (
        a20n.trim.MaxCG - a20n.trim.MinCG
    )
    magic2 = a20n.trim.MaxTrim - a20n.trim.MinCG * magic1
    CalculatedTrim = magic1 * cg + magic2
    return f"{round(abs(CalculatedTrim), 1)}{'UP' if CalculatedTrim > 0 else 'DN'}"


if __name__ == "__main__":
    settings = TakeoffInstance(
        **{
            "availRunway": 12795,
            "windHeading": 80,
            "windKts": 3,
            "tow": 62000,
            "baro": 1000,
            "oat": 5,
            "flaps": 1,
            "runwayHeading": 225,
            "runwayAltitude": 1411,
            "antiIce": False,
            "packs": True,
            "toga": False,
            "runwayCondition": 0,
        }
    )

    ret = FlexMath.calculateFlexDist(settings, a20n)
    v_speeds = FlexMath.CalculateVSpeeds(
        settings.availRunway,
        settings.requiredRunway,
        settings.tow,
        settings.flaps,
        settings.runwayAltitude,
        settings.isMeters,
        settings.isKG,
        a20n,
        settings.runwayCondition,
    )

    print(ret, v_speeds)
