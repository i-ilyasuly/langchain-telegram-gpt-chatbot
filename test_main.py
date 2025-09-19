# test_main.py
import pytest
from main import get_text, get_language_instruction, load_translations

@pytest.fixture(scope="session", autouse=True)
def load_test_translations():
    load_translations()

def test_get_text_kazakh():
    assert get_text("welcome_message", "kk") == "Assalamualaikum! Төмендегі батырмалар арқылы қажетті әрекетті таңдаңыз немесе сұрағыңызды жаза беріңіз:"
def test_get_text_russian():
    assert get_text("welcome_message", "ru") == "Assalamualaikum! Выберите действие с помощью кнопок ниже или просто напишите свой вопрос:"
def test_get_text_fallback():
    assert get_text("welcome_message", "en") == "Assalamualaikum! Төмендегі батырмалар арқылы қажетті әрекетті таңдаңыз немесе сұрағыңызды жаза беріңіз:"
def test_get_language_instruction():
    assert "қазақ тілінде" in get_language_instruction("kk")
    assert "орыс тілінде" in get_language_instruction("ru")
    assert "қазақ тілінде" in get_language_instruction("en")