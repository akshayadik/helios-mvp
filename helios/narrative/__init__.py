"""Narrative Engine with grounding verifier (S2.8, IN1).

Turns one CoE entry (S2.7) into a narrative whose every displayed claim cites
an item of that entry that exists and supports it. Gated by
``VCLFlag.COE_NARRATIVE``; ``l2c_llm`` picks the LLM or the template narrator.
"""
