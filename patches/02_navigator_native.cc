// Patch Guide for Native Navigator in Blink
// Target files:
// 1. third_party/blink/renderer/core/frame/navigator_concurrent_hardware.cc
// 2. third_party/blink/renderer/core/frame/navigator_device_memory.cc
// 3. third_party/blink/renderer/core/frame/navigator.cc

#include <cstdlib>

namespace blink {

// Override hardwareConcurrency natively
unsigned NavigatorConcurrentHardware::hardwareConcurrency() const {
  const char* hc_env = std::getenv("FP_HARDWARE_CONCURRENCY");
  if (hc_env) {
    int val = std::atoi(hc_env);
    if (val > 0) return static_cast<unsigned>(val);
  }
  // Fallback to real system cores
  return static_cast<unsigned>(base::SysInfo::NumberOfProcessors());
}

// Override deviceMemory natively (in GiB)
float NavigatorDeviceMemory::deviceMemory() const {
  const char* dm_env = std::getenv("FP_DEVICE_MEMORY");
  if (dm_env) {
    float val = static_cast<float>(std::atof(dm_env));
    if (val > 0.0f) return val;
  }
  // Fallback to real memory approximation
  return ApproximatedDeviceMemory();
}

// Strip navigator.webdriver completely
bool Navigator::webdriver() const {
  // Always return false even when CDP / remote debugging is enabled
  return false;
}

} // namespace blink
