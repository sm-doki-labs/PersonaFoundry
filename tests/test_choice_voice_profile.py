from importlib.resources import files

from character_factory_poc.contracts.formation import load_quality_profile


def test_choice_voice_profile_is_opt_in():
    assert load_quality_profile().profileId == "ko-text-prompt-long-v1"
    path = files("character_factory_poc").joinpath(
        "resources/persona-quality-profile-choice-voice-v2.json"
    )
    profile = load_quality_profile(path)
    assert profile.profileId == "ko-text-choice-voice-long-v2"
    assert profile.thresholds.longMaxChars == 8000
    assert not profile.thresholdsFrozen
    assert profile.modelBinding is None
