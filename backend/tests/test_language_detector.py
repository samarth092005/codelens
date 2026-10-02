from app.services.code_intelligence.language_detector import language_detector


def test_language_detection():
    # Python
    assert language_detector.detect_language("main.py") == "python"
    assert language_detector.detect_language("types.pyi") == "python"

    # JavaScript
    assert language_detector.detect_language("index.js") == "javascript"
    assert language_detector.detect_language("component.jsx") == "javascript"
    assert language_detector.detect_language("module.mjs") == "javascript"
    assert language_detector.detect_language("common.cjs") == "javascript"

    # TypeScript
    assert language_detector.detect_language("app.ts") == "typescript"
    assert language_detector.detect_language("Button.tsx") == "typescript"
    assert language_detector.detect_language("utils.mts") == "typescript"
    assert language_detector.detect_language("legacy.cts") == "typescript"

    # Unsupported / unknown
    assert language_detector.detect_language("README.md") == "unknown"
    assert language_detector.detect_language("styles.css") == "unknown"
    assert language_detector.detect_language("config.yaml") == "unknown"
    assert language_detector.detect_language("main.go") == "unknown"


def test_language_is_supported():
    assert language_detector.is_supported("python") is True
    assert language_detector.is_supported("javascript") is True
    assert language_detector.is_supported("typescript") is True
    assert language_detector.is_supported("unknown") is False
    assert language_detector.is_supported("rust") is False
