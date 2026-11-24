#pragma once
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace probe {
using Log = std::function<void(const std::string&)>;
struct Result { bool passed; std::string report; };
// Uses the port's exact calloc size and one host thread at a time.
// Touches only 32 MiB plus four sparse guest pages, never the whole arena.
Result run(const Log& log = {});
// Guest A8R8G8B8 Morton texture -> the actual shared RSX decoder -> RGBA8.
std::vector<uint8_t> diagnosticTexture();
}
