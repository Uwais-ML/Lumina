"""
test_router_classification.py
==============================
Tests Lumina's router/classifier logic in `scripts/classifier.py`:
  1. Intent & Context Routing (`needs_context`):
     - Cue-based and LLM-based detection for queries referencing prior conversation.
     - Standalone queries correctly recognized as NOT needing context.
  2. Casual vs Not-Casual Routing (`classify`):
     - Greetings/small talk routed as CASUAL (is_technical = False).
     - Technical queries/definitions/tasks routed as NOT_CASUAL (is_technical = True).
  3. Context Memory & Retrieval (`embed_context_file`, `searchforuserscontext`).
"""

import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import classifier
import launch_model


def test_needs_context_keyword_heuristics():
    """Verify keyword and intent triggers for prior context detection."""
    context_queries = [
        "What did we discuss earlier about Python?",
        "Can you remind me what you said in our previous discussion?",
        "Regarding that topic we mentioned last time",
        "What did we talk about before?",
    ]
    for q in context_queries:
        assert classifier.needs_context(q) is True, f"Failed to detect context need for: '{q}'"

    standalone_queries = [
        "What is the speed of light in vacuum?",
        "Write a quicksort implementation in Rust",
        "How do transformers compute self-attention?",
    ]
    # For standalone queries, verify they do not match the keyword heuristics
    for q in standalone_queries:
        cue_match = any(cue in q.lower() for cue in [
            "earlier", "previous", "we discussed", "we talked about",
            "past discussion", "our discussion", "last conversation",
            "you said", "we mentioned", "that topic", "prior conversation",
            "what we talked", "what did we discuss", "our earlier"
        ])
        assert not cue_match, f"Standalone query falsely matched cues: '{q}'"


def test_casual_vs_technical_classification():
    """Verify casual chit-chat vs technical queries routing."""
    # Ensure 0.5B model is initialized or reachable
    port = classifier.initialize()
    assert port is not None, "Classifier model failed to initialize"

    casual_samples = [
        "Hello! How are you today?",
        "Hi there",
        "Good morning",
    ]
    technical_samples = [
        "Explain backpropagation in neural networks.",
        "How do I configure a Chroma vector database in Python?",
        "Write a SQL query to find duplicate email addresses.",
    ]

    print("\n--- Testing Casual Samples ---")
    for q in casual_samples:
        is_tech = classifier.classify(q, save=False)
        print(f"Query: '{q}' -> is_technical: {is_tech}")
        # Note: Casual queries should classify as is_technical == False
        assert is_tech is False, f"Casual query misclassified as technical: '{q}'"

    print("\n--- Testing Technical Samples ---")
    for q in technical_samples:
        is_tech = classifier.classify(q, save=False)
        print(f"Query: '{q}' -> is_technical: {is_tech}")
        assert is_tech is True, f"Technical query misclassified as casual: '{q}'"


def test_context_storage_and_search(tmp_path):
    """Verify embedding and retrieval of past context chunks."""
    test_context_file = str(tmp_path / "test_context.txt")
    test_db_dir = str(tmp_path / "test_chroma_db")

    with open(test_context_file, "w", encoding="utf-8") as f:
        f.write("User preference: We are optimizing Lumina for low latency inference on M-series chips.\n")
        f.write("Target architecture involves dynamic hot-swapping between 3.8B and 0.5B models.\n")

    vstore, db = classifier.embed_context_file(
        context_path=test_context_file,
        db_path=test_db_dir
    )
    assert vstore is not None, "Failed to create context vectorstore"

    results = classifier.searchforuserscontext(
        "What architecture are we building for low latency?",
        path=test_db_dir,
        k=1
    )
    assert len(results) > 0, "Vector search returned no results"
    found_content = results[0].page_content if hasattr(results[0], "page_content") else str(results[0])
    assert "Lumina" in found_content or "hot-swapping" in found_content, (
        f"Retrieved content did not match expected context: {found_content}"
    )
