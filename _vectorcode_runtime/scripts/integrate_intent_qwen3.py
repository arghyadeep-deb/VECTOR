"""Integrate qwen3:8b classifier into governor pipeline.

Run this after training completes to wire up Stage 3.

Usage:
    python scripts/integrate_intent_qwen3.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


def integrate_classifier():
    """Add qwen3:8b classifier as Stage 3 in governor.py."""
    governor_path = Path("core/city/governor.py")

    if not governor_path.exists():
        logger.error(f"Governor not found: {governor_path}")
        return False

    # Read current governor.py
    content = governor_path.read_text(encoding="utf-8")

    # Check if already integrated
    if "IntentQwen3_8B" in content:
        logger.info("Qwen3 classifier already integrated")
        return True

    # Find insertion point (after embedding matcher, before LLM fallback)
    # Look for: "except Exception as e:\n        logger.warning(f\"[governor] Embedding matcher failed"
    marker = 'logger.warning(f"[governor] Embedding matcher failed, falling through to LLM: {e}")'

    if marker not in content:
        logger.error("Could not find insertion point in governor.py")
        return False

    # Prepare the integration code
    integration_code = '''
    # Stage 3: Qwen3 8B classifier (fine-tuned with LoRA)
    try:
        from core.city.intent_qwen3_8b import IntentQwen3_8B
        if not hasattr(classify_chat_intent, "_qwen3"):
            classify_chat_intent._qwen3 = IntentQwen3_8B()
        qwen3_result = await classify_chat_intent._qwen3.classify(text)
        if qwen3_result:
            _debug_classify_intent(text, "", f"QWEN3_MATCH -> {qwen3_result['district']} (conf={qwen3_result['confidence']:.3f})")
            return qwen3_result
    except Exception as e:
        logger.warning(f"[governor] Qwen3 classifier failed, falling through to LLM: {e}")

'''

    # Insert after the embedding matcher exception handler
    insert_pos = content.find(marker) + len(marker)
    new_content = content[:insert_pos] + "\n" + integration_code + content[insert_pos:]

    # Write back
    governor_path.write_text(new_content, encoding="utf-8")

    logger.info("✅ Qwen3 classifier integrated into governor.py (Stage 3)")
    logger.info("Pipeline now: Regex → Embedding → Qwen3 → LLM fallback")

    return True


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("INTEGRATE QWEN3 CLASSIFIER INTO GOVERNOR")
    print("=" * 70 + "\n")

    success = integrate_classifier()

    if success:
        print("\n✅ Integration complete!")
        print("\nNext steps:")
        print("1. Verify the model is trained: python core/city/intent_qwen3_8b.py --evaluate")
        print("2. Run integration test: python scripts/diag_tier6.py")
        print("3. Expected: 10/10 accuracy (improvement from 9/10)")
    else:
        print("\n❌ Integration failed")
        sys.exit(1)
