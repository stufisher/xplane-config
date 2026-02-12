import logging
import math
import os

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
FONTS = {
    "arial": "/System/Library/Fonts/Supplmental/Arial.ttf",
    "dseg": os.path.join(FONT_DIR, "DSEG7ClassicMini-Regular.ttf"),
    "symbols": os.path.join(FONT_DIR, "MaterialSymbolsOutlined_28pt-Medium.ttf"),
}
ARIAL = FONTS["arial"]


ILLUMINATED_COLORS = {
    "orange": (194, 104, 8),
    "green": (62, 171, 22),
    "blue": (46, 138, 209),
    "red": (255, 26, 23),
    "white": (240, 240, 240),
}


def create_image(size: int = 72):
    return Image.new("RGB", (size, size), "black")


def text_button(
    label: str = "",
    color: str = "white",
    text_size: int = 1,
    state: int = "",
    state_font=None,
    state_font_size: int = 1,
    notification: bool = False,
):
    img = create_image()
    draw = ImageDraw.Draw(img)

    cx, cy = img.width / 2, img.height / 2
    label_font = ImageFont.truetype(ARIAL, round(img.width * 0.15))
    draw.text(
        (cx, img.height * 0.18 * text_size),
        label,
        font=label_font,
        align="center",
        anchor="ms",
        fill=color,
    )

    if state:
        if not isinstance(state, str):
            state = str(state)
        font_name = FONTS[state_font] if state_font else ARIAL
        font = ImageFont.truetype(font_name, round(img.width * 0.3 * state_font_size))
        tcx, tcy, w, h = draw.textbbox(
            (0, 0),
            state,
            font=font,
        )
        draw.text(
            (cx - w / 2, cy - h / 2),
            state,
            font=font,
            fill=color,
        )

    if notification:
        draw.ellipse((10, img.height - 20, 20, img.height - 10), fill="red")

    return img


def illuminated_button(
    label: str = "Test",
    text: str = "OFF",
    text_font: str = "arial",
    rectangle: bool = True,
    color: str = "white",
    state: bool = False,
    secondary_text: str = "FAULT",
    secondary_color: str = "red",
    secondary_state: bool = False,
):
    img = create_image()
    draw = ImageDraw.Draw(img)

    label_font = ImageFont.truetype(ARIAL, round(img.width * 0.15))
    draw.text(
        (img.width / 2, 14),
        label,
        font=label_font,
        align="center",
        anchor="ms",
        fill="white",
    )

    border = 8
    off_color = (25, 25, 25)
    if rectangle:
        draw.rectangle(
            (border, img.height * 3 / 5, img.width - border, img.height - border),
            outline=ILLUMINATED_COLORS[color] if state else off_color,
            width=2,
        )

    font_scale = 1 if rectangle else 2
    font = ImageFont.truetype(FONTS[text_font], round(img.width * 0.23 * font_scale))
    draw.text(
        (img.width / 2, img.height * 3 / 5 + 17 * font_scale),
        text,
        font=font,
        align="center",
        anchor="ms",
        fill=ILLUMINATED_COLORS[color] if state else off_color,
    )

    if secondary_text:
        font = ImageFont.truetype(ARIAL, round(img.width * 0.20))
        off_color = (15, 15, 15)
        draw.text(
            (img.width / 2, img.height * 0.5),
            secondary_text,
            font=font,
            align="center",
            anchor="ms",
            fill=ILLUMINATED_COLORS[secondary_color] if secondary_state else off_color,
        )
    return img


def push_button(label: str = "CTL", color="green", state: bool = False):
    img = create_image()
    draw = ImageDraw.Draw(img)

    offset = img.height / 2 - 25
    fill_color = color if state else (25, 25, 25)

    border = 15

    draw.line(
        (border, 5 + offset, img.width - border, 5 + offset), fill=fill_color, width=3
    )
    draw.line(
        (border, 12 + offset, img.width - border, 12 + offset), fill=fill_color, width=3
    )
    draw.line(
        (border, 19 + offset, img.width - border, 19 + offset), fill=fill_color, width=3
    )

    font = ImageFont.truetype(ARIAL, round(img.width * 0.25))
    draw.text(
        (img.width / 2, 45 + offset),
        label,
        font=font,
        align="center",
        anchor="ms",
        fill="white",
    )

    return img


def xy_from_angle(x: float, y: float, angle: int, length: float):
    """
    angle: int (degrees)
    """
    x2 = x + length * math.cos(math.radians(angle))
    y2 = y + length * math.sin(math.radians(angle))

    return x2, y2


def angle_to_positive(angle: int):
    return angle % 360


def rotary_control(label="Options", options=["ONE", "TWO", "THRE"], state=0):
    if not isinstance(state, int):
        try:
            state = int(state)
        except TypeError:
            state = 0

    if state > len(options) - 1:
        logger.warning(f"rotary control: {label} state={state} options={options}")
        state = len(options) - 1

    angles = {2: [-60, 60], 3: [-60, 0, 60], 4: [-90, -35, 35, 90]}
    img = create_image(72 * 3)
    draw = ImageDraw.Draw(img)

    object_size = img.width * 0.3
    vertical_offset = img.height * 0.28
    cx = img.width / 2
    cy = img.height / 2 + vertical_offset

    label_font = ImageFont.truetype(ARIAL, round(img.width * 0.15))
    # label_font = ImageFont.truetype(ARIAL, round(img.width * 0.18))
    draw.text(
        (cx, img.width * 0.18),
        label,
        font=label_font,
        align="center",
        anchor="ms",
        fill="white",
    )
    font = ImageFont.truetype(ARIAL, round(img.width * 0.15))
    len_options = len(options)
    angles = angles[len_options]
    for i in range(len_options):
        angle = angle_to_positive(angles[i] - 90)
        x2, y2 = xy_from_angle(cx, cy, angle, length=object_size / 2 + img.width * 0.04)

        ellipse_size = img.width * 0.024
        draw.ellipse(
            (
                x2 - ellipse_size,
                y2 - ellipse_size,
                x2 + ellipse_size,
                y2 + ellipse_size,
            ),
            fill="gray",
        )

        x2, y2 = xy_from_angle(
            cx, cy, angle, length=object_size / 2 + object_size * 0.6
        )
        draw.text(
            (x2, y2),
            options[i],
            font=font,
            align="center",
            anchor="ms",
            fill=(55, 124, 161),
        )

    bbox = (
        cx - object_size / 2,
        cy - object_size / 2,
        cx + object_size / 2,
        cy + object_size / 2,
    )
    draw.ellipse(bbox, fill="gray")

    angle = angle_to_positive(angles[state] - 90)
    x2, y2 = xy_from_angle(cx, cy, angle, length=object_size / 2 - img.width * 0.05)

    ellipse_size = img.width * 0.02
    draw.ellipse(
        (
            x2 - ellipse_size,
            y2 - ellipse_size,
            x2 + ellipse_size,
            y2 + ellipse_size,
        ),
        fill="white",
    )

    return img


def arc_gauge(
    label: str = "Gauge",
    state=2.5,
    gauge_range=[0, 3],
    ok_range=[0, 1],
    is_normalised=False,
):
    if not isinstance(state, float):
        try:
            state = float(state)
        except TypeError:
            state = 0.0
    img = create_image(72 * 3)
    draw = ImageDraw.Draw(img)

    cx = img.width / 2
    label_offset = img.width * 0.18
    label_font = ImageFont.truetype(ARIAL, round(img.width * 0.15))
    _, _, _, h = draw.textbbox(
        (cx, label_offset),
        label,
        font=label_font,
    )
    draw.text(
        (cx, label_offset),
        label,
        font=label_font,
        align="center",
        anchor="ms",
        fill="white",
    )

    width = int(img.height * 0.08)
    border = 8
    arc_height = img.height - h - border
    draw.arc(
        (
            cx - arc_height - arc_height / 2,
            h,
            cx + arc_height - arc_height / 2,
            arc_height * 2 + h,
        ),
        -90,
        0,
        width=width,
        fill="white",
    )

    gauge_font = ImageFont.truetype(ARIAL, round(img.width * 0.22))
    _, _, gw, gh = draw.textbbox(
        (0, 0),
        str(gauge_range[0]),
        font=gauge_font,
        align="center",
        anchor="ms",
    )
    draw.text(
        (img.width - gw - border, img.height - gh - border),
        str(gauge_range[0]),
        font=gauge_font,
        align="center",
        anchor="ms",
        fill=(170, 170, 170),
    )
    draw.text(
        (gw + border, h + gh + border),
        str(gauge_range[1]),
        font=gauge_font,
        align="center",
        anchor="ms",
        fill=(170, 170, 170),
    )

    total_range = gauge_range[1] - gauge_range[0]
    offset = gauge_range[0]
    normalised_state = (
        round(state * total_range + offset, 1) if is_normalised else state
    )

    state_font = ImageFont.truetype(FONTS["dseg"], round(img.width * 0.25))
    draw.text(
        (border, img.height * 0.7),
        str(normalised_state),
        font=state_font,
        fill="white",
    )

    ok_start = (ok_range[0] - offset) / total_range
    ok_end = (ok_range[1] - offset) / total_range
    draw.arc(
        (
            cx - arc_height - arc_height / 2,
            h,
            cx + arc_height - arc_height / 2,
            arc_height * 2 + h,
        ),
        -ok_end * 90,
        -ok_start * 90,
        width=width,
        fill=ILLUMINATED_COLORS["green"],
    )

    scaled_state = (normalised_state - offset) / total_range
    draw.arc(
        (
            cx - arc_height - arc_height / 2,
            h,
            cx + arc_height - arc_height / 2,
            arc_height * 2 + h,
        ),
        -scaled_state * 90 - 2,
        -scaled_state * 90 + 2,
        width=int(width * 2.5),
        fill="white",
    )

    return img


KEY_TYPES = {
    "illuminated_button": illuminated_button,
    "push_button": push_button,
    "rotary_control": rotary_control,
    "text_button": text_button,
    "arc_gauge": arc_gauge,
}

if __name__ == "__main__":
    # img = illuminated_button(state=False)
    # img.show()

    # img2 = push_button(state=True)
    # img2.show()

    # img3 = rotary()
    # img3 = img3.resize((72, 72), Image.LANCZOS)
    # img3.show()

    img4 = arc_gauge()
    img4 = img4.resize((72, 72), Image.LANCZOS)
    img4.show()
