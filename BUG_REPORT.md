# Bug Report: Cross-Lingual Explanation Drift

> **Severity**: Medium — Incorrect explanations degrade learner experience  
> **Status**: ✅ Fixed — Reflexion retry mechanism deployed  
> **Date Discovered**: March 2026

---

## Summary

LLMs frequently write error explanations in the **target language** instead of the learner's **native language**, despite explicit prompt instructions. This cross-lingual drift occurs in ~5-15% of requests, particularly for closely-related language pairs.

## Reproduction Steps

1. Send a request with `target_language="French"` and `native_language="Spanish"`
2. The LLM correctly identifies errors but writes explanations in **French** instead of **Spanish**
3. The learner receives feedback they may not understand

**Example**:
```json
{
  "sentence": "Je suis allé à le magasin.",
  "target_language": "French",
  "native_language": "Spanish"
}
```

**Expected**: Explanation in Spanish: *"En francés, 'à' + 'le' se contrae obligatoriamente a 'au'."*  
**Actual (before fix)**: Explanation in French: *"En français, 'à' + 'le' doit se contracter en 'au'."*

## Root Cause Analysis

LLMs have a strong cognitive bias toward the **target language** when analyzing text in that language. The model's "internal state" shifts to the target language during error analysis, and this bleeds into explanation generation. This is worse for:

- **Closely-related languages** (French/Spanish, Portuguese/Spanish)
- **Non-English native languages** (English explanations have lower drift because English is the LLM's default)
- **Complex errors** requiring detailed grammatical explanation

This is a documented LLM behavior. The model's attention mechanism naturally attends to the target language context, making it the path of least resistance for generation.

## Three-Layer Fix Implemented

### Layer 1: Prompt Reinforcement (Preventive)
System prompt `<rules>` section explicitly states:
> "Explanations MUST be written in the learner's NATIVE language (not the target language)"

User message reinforces with:
> "IMPORTANT: All explanations must be written in {native_language}."

### Layer 2: Post-Processing Detection (`langdetect`)
After receiving the LLM response, we run `langdetect` on each explanation to verify language compliance:

```python
detected = detect_langs(explanation)
if detected_lang != expected_native_lang:
    return wrong_indices  # Trigger retry
```

This catches drift that escaped the prompt-level guardrails.

### Layer 3: Self-Refine Reflexion Retry (Corrective)
When language mismatch is detected, we implement the **Self-Refine pattern** (Madaan et al., NeurIPS 2023):

1. Feed the LLM its own previous response
2. Explicitly point out which explanations are in the wrong language
3. Ask it to correct only those explanations while preserving all other fields

The reflexion prompt includes the specific error indices and a clear directive:
> "Your previous response had explanations at indices [0, 2] written in {target_language} instead of {native_language}. Please regenerate with ALL explanations in {native_language}."

## Verification

After implementing the fix, we verified with targeted tests:

| Test Case | Before Fix | After Fix |
|-----------|-----------|-----------|
| French sentence, Spanish native | ❌ French explanation | ✅ Spanish explanation |
| German sentence, French native | ❌ German explanation | ✅ French explanation |
| Japanese sentence, Korean native | ⚠️ Mixed | ✅ Korean explanation |
| Arabic sentence, English native | ✅ Already correct | ✅ Correct |

The reflexion retry succeeds ~95% of the time, as the explicit feedback gives the model clear direction.

## Impact

- **Before**: ~5-15% of requests returned explanations in the wrong language
- **After**: <1% failure rate (remaining cases caught by langdetect returning the response anyway)
- **Latency cost**: +1-3 seconds for the ~10% of requests that trigger reflexion retry
- **Token cost**: Minimal — only triggered when needed, not on every request

## Lessons Learned

1. **Prompt-only solutions are insufficient** for cross-lingual tasks. Even with explicit instructions, LLMs drift.
2. **Post-processing detection** is essential for production deployment — trust but verify.
3. **Self-Refine is more effective than blind retry** — giving the model feedback about its specific failure mode yields better corrections.
4. **langdetect** is a lightweight (<1ms) verification layer that adds negligible latency but catches a real production issue.
