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

/// Compute Root Mean Square (RMS) energy of an audio buffer.
#[pyfunction]
fn audio_rms(samples: Vec<f32>) -> PyResult<f32> {
    if samples.is_empty() {
        return Ok(0.0);
    }
    let sum_sq: f32 = samples.iter().map(|&s| s * s).sum();
    Ok((sum_sq / samples.len() as f32).sqrt())
}

/// Fast VAD energy check: returns true if audio RMS exceeds threshold.
#[pyfunction]
fn fast_vad_energy(samples: Vec<f32>, threshold: f32) -> PyResult<bool> {
    if samples.is_empty() {
        return Ok(false);
    }
    let sum_sq: f32 = samples.iter().map(|&s| s * s).sum();
    let rms = (sum_sq / samples.len() as f32).sqrt();
    Ok(rms >= threshold)
}

/// Batch compute cosine similarities between a single query vector and N candidate vectors.
#[pyfunction]
fn batch_cosine_similarity(query: Vec<f32>, candidates: Vec<Vec<f32>>) -> PyResult<Vec<f32>> {
    if query.is_empty() || candidates.is_empty() {
        return Ok(Vec::new());
    }

    let q_norm_sq: f32 = query.iter().map(|&x| x * x).sum();
    let q_norm = q_norm_sq.sqrt();
    if q_norm == 0.0 {
        return Ok(vec![0.0; candidates.len()]);
    }

    let mut results = Vec::with_capacity(candidates.len());
    for cand in candidates {
        if cand.len() != query.len() {
            results.push(0.0);
            continue;
        }

        let mut dot = 0.0f32;
        let mut cand_norm_sq = 0.0f32;

        for (q, c) in query.iter().zip(cand.iter()) {
            dot += q * c;
            cand_norm_sq += c * c;
        }

        let c_norm = cand_norm_sq.sqrt();
        if c_norm == 0.0 {
            results.push(0.0);
        } else {
            results.push(dot / (q_norm * c_norm));
        }
    }

    Ok(results)
}

/// Return the indices of the top-k highest scores in descending order.
#[pyfunction]
fn top_k_indices(scores: Vec<f32>, k: usize) -> PyResult<Vec<usize>> {
    if scores.is_empty() || k == 0 {
        return Ok(Vec::new());
    }

    let mut indexed: Vec<(usize, f32)> = scores.into_iter().enumerate().collect();
    // Sort descending by score
    indexed.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    let top = indexed.into_iter().take(k).map(|(idx, _)| idx).collect();
    Ok(top)
}

#[pymodule]
fn raphael_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(perceptual_diff, m)?)?;
    m.add_function(wrap_pyfunction!(cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(fast_token_estimate, m)?)?;
    m.add_function(wrap_pyfunction!(audio_rms, m)?)?;
    m.add_function(wrap_pyfunction!(fast_vad_energy, m)?)?;
    m.add_function(wrap_pyfunction!(batch_cosine_similarity, m)?)?;
    m.add_function(wrap_pyfunction!(top_k_indices, m)?)?;
    Ok(())
}
