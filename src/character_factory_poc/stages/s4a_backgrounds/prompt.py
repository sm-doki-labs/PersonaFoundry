"""인물 없는 세로 배경 사진의 생성 지시."""

PLATE_NEGATIVE = "people, person, text, watermark, logo"


def build_plate_prompt(
    plate_brief: str, place: str = "", time_of_day: str = "", mood: str = ""
) -> str:
    return " ".join(
        [
            "Photorealistic empty background plate of a realistic modern Korean place.",
            f"Place: {place}. Time: {time_of_day}. Light and color: {mood}.",
            plate_brief,
            "Vertical 9:16 composition, preserve room for a foreground subject to be added later.",
            "No people, no person, no human silhouettes, no reflections of people.",
            "No text, no watermark, no logo, no real brand names or recognizable fictional works.",
        ]
    )
