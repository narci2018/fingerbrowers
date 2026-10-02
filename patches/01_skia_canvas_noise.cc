// Patch Guide for Canvas Noise in Skia (third_party/skia/src/core/SkCanvas.cpp)
// This code demonstrates the core noise injection logic used in commercial anti-detect engines.
//
// In SkCanvas::readPixels or SkCanvas::onDrawRect:
//
#include <cstdlib>
#include <cstdint>

namespace {
// Deterministic fast PRNG (Xorshift32)
uint32_t g_fp_seed = 0;
bool g_fp_seed_initialized = false;

uint32_t GetProfileSeed() {
    if (!g_fp_seed_initialized) {
        const char* seed_env = std::getenv("FP_CANVAS_SEED");
        if (seed_env) {
            g_fp_seed = static_cast<uint32_t>(std::strtoul(seed_env, nullptr, 10));
        } else {
            g_fp_seed = 0;
        }
        g_fp_seed_initialized = true;
    }
    return g_fp_seed;
}

uint32_t XorShift32(uint32_t& state) {
    uint32_t x = state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    state = x;
    return x;
}

// Injects sub-pixel / LSB color noise into pixel buffers
void InjectNoiseToBitmap(uint8_t* pixels, size_t row_bytes, int width, int height) {
    uint32_t seed = GetProfileSeed();
    if (seed == 0) return; // Feature disabled

    uint32_t state = seed;
    for (int y = 0; y < height; ++y) {
        uint8_t* row = pixels + (y * row_bytes);
        for (int x = 0; x < width; ++x) {
            // Apply micro-noise only to a few pixels deterministically
            if ((XorShift32(state) % 100) < 3) { // 3% of pixels
                int channel = XorShift32(state) % 3; // R, G, or B
                row[x * 4 + channel] ^= 1; // Flip LSB (undetectable visually, unique hash)
            }
        }
    }
}
} // namespace
