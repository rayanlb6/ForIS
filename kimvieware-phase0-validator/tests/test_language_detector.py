from validators.language_detector import LanguageDetector


def test_detect_python(tmp_path):
    # Create a simple python project
    (tmp_path / 'main.py').write_text('print("hello")')
    res = LanguageDetector.detect(tmp_path)
    assert res['language'] == 'python'
    assert res['entry_point'] is not None
    assert res['entry_point'].name.endswith('.py')


def test_detect_c(tmp_path):
    (tmp_path / 'main.c').write_text('int main() { return 0; }')
    (tmp_path / 'util.h').write_text('// header')
    res = LanguageDetector.detect(tmp_path)
    assert res['language'] in ('c', 'cpp') or res['language'] == 'c'
    assert res['entry_point'] is not None


def test_detect_cpp(tmp_path):
    (tmp_path / 'main.cpp').write_text('int main() { return 0; }')
    (tmp_path / 'helper.hpp').write_text('// helper')
    res = LanguageDetector.detect(tmp_path)
    assert res['language'] == 'cpp' or res['language'] == 'c'
    assert res['entry_point'] is not None
