use pyo3::prelude::*;

/// Compute the mean absolute difference ratio between two image byte buffers.
/// Returns a float in [0.0, 1.0] representing the percentage difference.
#[pyfunction]
fn perceptual_diff(buf_a: &[u8], buf_b: &[u8]) -> PyResult<f64> {
    if buf_a.is_empty() || buf_b.is_empty() || buf_a.len() != buf_b.len() {
        return Ok(1.0);
    }

    let diff_sum: u64 = buf_a
        .iter()
        .zip(buf_b.iter())
        .map(|(&a, &b)| (a as i32 - b as i32).unsigned_abs() as u64)
        .sum();

    let max_possible = buf_a.len() as f64 * 255.0;
    Ok(diff_sum as f64 / max_possible)
}

/// Compute cosine similarity between two float vectors using SIMD-friendly vector math.
#[pyfunction]
fn cosine_similarity(vec_a: Vec<f32>, vec_b: Vec<f32>) -> PyResult<f32> {
    if vec_a.len() != vec_b.len() || vec_a.is_empty() {
        return Ok(0.0);
    }

    let mut dot = 0.0f32;
    let mut norm_a = 0.0f32;
    let mut norm_b = 0.0f32;

    for (a, b) in vec_a.iter().zip(vec_b.iter()) {
        dot += a * b;
        norm_a += a * a;
        norm_b += b * b;
    }

    let denom = norm_a.sqrt() * norm_b.sqrt();
    if denom == 0.0 {
        Ok(0.0)
    } else {
        Ok(dot / denom)
    }
}

/// Fast token count estimator based on word and punctuation clustering.
#[pyfunction]
fn fast_token_estimate(text: &str) -> PyResult<usize> {
    if text.is_empty() {
        return Ok(0);
    }
    // Standard rule-of-thumb: ~4 chars per token in English text
    let words = text.split_whitespace().count();
    let char_count = text.len();
    let estimate = (words as f64 * 1.33).max(char_count as f64 / 3.8) as usize;
    Ok(estimate.max(1))
}

#[pymodule]
fn raphael_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(perceptual_diff, m)?)?;
    m.add_function(wrap_pyfunction!(cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(fast_token_estimate, m)?)?;
    Ok(())
}
